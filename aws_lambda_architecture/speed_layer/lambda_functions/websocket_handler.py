"""
AWS Lambda function for handling Polygon.io WebSocket connections
Processes real-time tick data and feeds into Kinesis Data Streams

MVP SPEED LAYER ARCHITECTURE:
WebSocket Handler → Kinesis Streams → Firehose → Aurora Database

FUTURE ENHANCEMENTS (Post-MVP):
- Kinesis Analytics for real-time OHLCV aggregation  
- Custom Lambda for indicator processing (consolidation, pivots)
- SNS for signal distribution
- Multiple timeframe outputs (5m, 15m, 1h, 4h, etc.)
"""

import json
import boto3
import asyncio
import websockets
import logging
from datetime import datetime
from typing import Dict, Any, List
import os
from decimal import Decimal

# Import shared utilities
import sys
sys.path.append('/opt/python')
from shared.clients.kinesis_client import KinesisClient
from shared.clients.redis_client import RedisClient
from shared.models.data_models import TickData, OHLCVData

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for WebSocket tick data processing
    
    This function can be triggered by:
    1. EventBridge schedule (to maintain WebSocket connections)
    2. Manual invocation for testing
    3. API Gateway WebSocket events
    """
    
    try:
        # Get symbols to subscribe to
        symbols = event.get('symbols', get_default_symbols())
        
        # Initialize clients
        kinesis_client = KinesisClient(
            stream_name=os.environ['KINESIS_STREAM_NAME']
        )
        redis_client = RedisClient(
            endpoint=os.environ['REDIS_ENDPOINT']
        )
        
        # Run the WebSocket client
        asyncio.run(run_websocket_client(symbols, kinesis_client, redis_client))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'WebSocket handler completed successfully',
                'symbols': symbols,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'WebSocket handler failed',
                'message': str(e)
            })
        }


async def run_websocket_client(
    symbols: List[str], 
    kinesis_client: KinesisClient,
    redis_client: RedisClient
):
    """
    Run the WebSocket client to receive real-time tick data
    """
    api_key = os.environ['POLYGON_API_KEY']
    websocket_url = f"wss://socket.polygon.io/stocks"
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            # Authenticate
            auth_message = {
                "action": "auth",
                "params": api_key
            }
            await websocket.send(json.dumps(auth_message))
            
            # Wait for auth response
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data[0].get('status') != 'auth_success':
                raise Exception(f"Authentication failed: {auth_data}")
            
            logger.info("WebSocket authentication successful")
            
            # Subscribe to tick data for symbols
            subscribe_message = {
                "action": "subscribe",
                "params": f"T.{','.join(symbols)}"  # T.AAPL,T.MSFT,etc.
            }
            await websocket.send(json.dumps(subscribe_message))
            
            logger.info(f"Subscribed to {len(symbols)} symbols")
            
            # Process incoming messages
            message_count = 0
            start_time = datetime.utcnow()
            
            # Run for a limited time in Lambda (14 minutes max)
            timeout_seconds = int(os.environ.get('WEBSOCKET_TIMEOUT', '840'))  # 14 minutes
            
            try:
                while True:
                    # Check timeout
                    if (datetime.utcnow() - start_time).seconds > timeout_seconds:
                        logger.info(f"Timeout reached, processed {message_count} messages")
                        break
                    
                    # Receive message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    
                    # Process message
                    await process_websocket_message(
                        message, 
                        kinesis_client, 
                        redis_client
                    )
                    
                    message_count += 1
                    
                    # Log progress periodically
                    if message_count % 100 == 0:
                        logger.info(f"Processed {message_count} messages")
                        
            except asyncio.TimeoutError:
                logger.info("WebSocket receive timeout - connection may be idle")
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                
    except Exception as e:
        logger.error(f"WebSocket client error: {str(e)}")
        raise


async def process_websocket_message(
    message: str,
    kinesis_client: KinesisClient,
    redis_client: RedisClient
):
    """
    Process a single WebSocket message
    """
    try:
        data = json.loads(message)
        
        # Handle different message types
        for item in data:
            message_type = item.get('ev')  # Event type
            
            if message_type == 'T':  # Trade message
                await process_trade_message(item, kinesis_client, redis_client)
            elif message_type == 'Q':  # Quote message
                await process_quote_message(item, kinesis_client)
            elif message_type == 'status':
                logger.info(f"Status message: {item}")
            
    except Exception as e:
        logger.error(f"Error processing WebSocket message: {str(e)}")
        # Continue processing other messages


async def process_trade_message(
    trade_data: Dict[str, Any],
    kinesis_client: KinesisClient,
    redis_client: RedisClient
):
    """
    Process a trade message (tick data)
    """
    try:
        # Extract trade data
        tick = TickData(
            symbol=trade_data['sym'],
            price=Decimal(str(trade_data['p'])),
            volume=int(trade_data['s']),
            timestamp=datetime.fromtimestamp(trade_data['t'] / 1000),
            exchange=trade_data.get('x'),
            conditions=trade_data.get('c', [])
        )
        
        # MVP: Direct tick data to Kinesis (Firehose will batch to Aurora)
        await kinesis_client.put_record(
            data=tick.dict(),
            partition_key=tick.symbol
        )
        
        # MVP: Basic aggregation in Redis for instant API responses
        await update_minute_ohlcv_redis(tick, redis_client)
        
        # Update Redis with latest price (for fast lookups)
        await redis_client.set_latest_price(tick.symbol, tick.price)
        
        # Update Redis with tick count (for monitoring)
        await redis_client.increment_counter(f"ticks:{tick.symbol}")
        
    except Exception as e:
        logger.error(f"Error processing trade message: {str(e)}")


async def process_quote_message(
    quote_data: Dict[str, Any],
    kinesis_client: KinesisClient
):
    """
    Process a quote message (bid/ask data)
    """
    try:
        # Send quote data to separate Kinesis stream if needed
        # For MVP, we might focus on trades only
        pass
        
    except Exception as e:
        logger.error(f"Error processing quote message: {str(e)}")


async def update_minute_ohlcv_redis(tick: TickData, redis_client: RedisClient):
    """
    MVP: Simple minute-level OHLCV aggregation in Redis
    This provides instant API responses while Firehose handles bulk storage
    
    FUTURE: Replace with Kinesis Analytics for multiple timeframes
    """
    try:
        # Create minute bucket key (e.g., "ohlcv:AAPL:2025-09-17T10:45:00")
        minute_timestamp = tick.timestamp.replace(second=0, microsecond=0)
        redis_key = f"ohlcv:{tick.symbol}:{minute_timestamp.isoformat()}"
        
        # Get existing minute data or initialize
        existing_data = await redis_client.get(redis_key)
        
        if existing_data:
            ohlcv = json.loads(existing_data)
            # Update existing minute data
            ohlcv['high'] = max(float(ohlcv['high']), float(tick.price))
            ohlcv['low'] = min(float(ohlcv['low']), float(tick.price))
            ohlcv['close'] = float(tick.price)  # Latest price
            ohlcv['volume'] += tick.volume
            ohlcv['last_updated'] = tick.timestamp.isoformat()
        else:
            # Initialize new minute data
            ohlcv = {
                'symbol': tick.symbol,
                'open': float(tick.price),
                'high': float(tick.price),
                'low': float(tick.price),
                'close': float(tick.price),
                'volume': tick.volume,
                'timestamp': minute_timestamp.isoformat(),
                'interval': '1m',
                'last_updated': tick.timestamp.isoformat()
            }
        
        # Store back in Redis with 2-hour TTL (MVP: keep recent data only)
        await redis_client.setex(redis_key, 7200, json.dumps(ohlcv))
        
        # Also update "current_minute" key for easy API access
        current_key = f"current_minute:{tick.symbol}"
        await redis_client.setex(current_key, 120, json.dumps(ohlcv))
        
    except Exception as e:
        logger.error(f"Error updating minute OHLCV in Redis: {str(e)}")


async def placeholder_indicator_processing(tick: TickData, redis_client: RedisClient):
    """
    PLACEHOLDER: Future indicator processing
    
    POST-MVP ENHANCEMENTS:
    - Consolidation detection (price range analysis)
    - Pivot point calculation (support/resistance)
    - Volume profile analysis
    - Breakout detection
    - Trend analysis
    
    For now, this is just a placeholder to show where 
    real-time indicators would be calculated
    """
    # FUTURE: Implement consolidation detection
    # if detect_consolidation(tick.symbol, tick.price):
    #     await publish_consolidation_signal(tick.symbol, redis_client)
    
    # FUTURE: Implement pivot analysis  
    # if detect_pivot_break(tick.symbol, tick.price):
    #     await publish_pivot_signal(tick.symbol, redis_client)
    
    pass  # MVP: Skip indicator processing


def get_default_symbols() -> List[str]:
    """
    Get default symbols to subscribe to
    """
    # This could be fetched from Aurora or environment variables
    default_symbols = os.environ.get(
        'DEFAULT_SYMBOLS', 
        'AAPL,MSFT,GOOGL,AMZN,TSLA,META,NVDA,NFLX,PYPL,DIS'
    ).split(',')
    
    return [symbol.strip() for symbol in default_symbols]


# For local testing
if __name__ == "__main__":
    # Local test run
    test_event = {
        'symbols': ['AAPL', 'MSFT']
    }
    
    # Mock context
    class MockContext:
        def get_remaining_time_in_millis(self):
            return 300000  # 5 minutes
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
