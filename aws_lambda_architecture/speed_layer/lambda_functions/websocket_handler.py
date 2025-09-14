"""
AWS Lambda function for handling Polygon.io WebSocket connections
Processes real-time tick data and feeds into Kinesis Data Streams
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
        
        # Send to Kinesis for stream processing
        await kinesis_client.put_record(
            data=tick.dict(),
            partition_key=tick.symbol
        )
        
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
