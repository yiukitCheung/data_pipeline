"""
MVP Interval Aggregator Lambda Function

Simple approach for multi-timeframe OHLCV generation:
- Triggered by EventBridge schedule every minute
- Reads 1-minute OHLCV data from Redis  
- Generates 5m, 15m, 30m, 1h, 4h, 8h intervals
- Stores in Redis for API access
- Eventually stores in Aurora via Firehose

FUTURE ENHANCEMENTS (Post-MVP):
- Replace with Kinesis Analytics for real-time processing
- Add indicator calculations
- Add signal generation and publishing
"""

import json
import boto3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from decimal import Decimal
import os

# Import shared utilities
import sys
sys.path.append('/opt/python')
from shared.clients.redis_client import RedisClient
from shared.clients.kinesis_client import KinesisClient
from shared.models.data_models import OHLCVData

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class IntervalAggregator:
    def __init__(self):
        self.redis_client = RedisClient(endpoint=os.environ['REDIS_ENDPOINT'])
        self.kinesis_client = KinesisClient(stream_name=os.environ['KINESIS_STREAM_NAME'])
        
        # Define intervals for aggregation
        self.intervals = {
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1h': 60,
            '4h': 240,
            '8h': 480
        }
    
    async def aggregate_intervals(self, symbols: List[str]) -> Dict[str, int]:
        """
        Aggregate 1-minute data into multiple timeframes
        
        Returns:
            Dict with interval -> records_processed count
        """
        results = {}
        
        for interval_name, minutes in self.intervals.items():
            try:
                records_processed = await self.process_interval(symbols, interval_name, minutes)
                results[interval_name] = records_processed
                logger.info(f"Processed {records_processed} records for {interval_name}")
            except Exception as e:
                logger.error(f"Error processing {interval_name}: {str(e)}")
                results[interval_name] = 0
        
        return results
    
    async def process_interval(self, symbols: List[str], interval_name: str, minutes: int) -> int:
        """
        Process a specific interval for all symbols
        """
        records_processed = 0
        current_time = datetime.utcnow()
        
        # Calculate the interval boundary (e.g., for 5m: 10:15, 10:20, 10:25...)
        interval_start = self.get_interval_start(current_time, minutes)
        interval_end = interval_start + timedelta(minutes=minutes)
        
        for symbol in symbols:
            try:
                ohlcv_data = await self.aggregate_symbol_interval(
                    symbol, interval_start, interval_end, interval_name, minutes
                )
                
                if ohlcv_data:
                    # Store in Redis
                    await self.store_interval_data(ohlcv_data)
                    
                    # Send to Kinesis for Aurora storage
                    await self.send_to_kinesis(ohlcv_data)
                    
                    records_processed += 1
                    
            except Exception as e:
                logger.error(f"Error processing {symbol} for {interval_name}: {str(e)}")
        
        return records_processed
    
    async def aggregate_symbol_interval(
        self, 
        symbol: str, 
        start_time: datetime, 
        end_time: datetime, 
        interval_name: str, 
        minutes: int
    ) -> Optional[OHLCVData]:
        """
        Aggregate 1-minute data for a symbol into the specified interval
        """
        try:
            # Get all 1-minute records in the interval
            minute_data = []
            current_minute = start_time
            
            while current_minute < end_time:
                minute_key = f"ohlcv:{symbol}:{current_minute.isoformat()}"
                data = await self.redis_client.get(minute_key)
                
                if data:
                    minute_ohlcv = json.loads(data)
                    minute_data.append(minute_ohlcv)
                
                current_minute += timedelta(minutes=1)
            
            if not minute_data:
                return None
            
            # Aggregate the minute data
            aggregated = self.calculate_ohlcv_from_minutes(minute_data, symbol, start_time, interval_name)
            return aggregated
            
        except Exception as e:
            logger.error(f"Error aggregating {symbol} {interval_name}: {str(e)}")
            return None
    
    def calculate_ohlcv_from_minutes(
        self, 
        minute_data: List[Dict], 
        symbol: str, 
        timestamp: datetime, 
        interval: str
    ) -> OHLCVData:
        """
        Calculate OHLCV from multiple 1-minute records
        """
        if not minute_data:
            raise ValueError("No minute data provided")
        
        # Sort by timestamp to ensure correct order
        minute_data.sort(key=lambda x: x['timestamp'])
        
        # Calculate aggregated values
        open_price = Decimal(str(minute_data[0]['open']))
        close_price = Decimal(str(minute_data[-1]['close']))
        high_price = max(Decimal(str(data['high'])) for data in minute_data)
        low_price = min(Decimal(str(data['low'])) for data in minute_data)
        total_volume = sum(data['volume'] for data in minute_data)
        
        return OHLCVData(
            symbol=symbol,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=total_volume,
            timestamp=timestamp,
            interval=interval
        )
    
    async def store_interval_data(self, ohlcv_data: OHLCVData):
        """
        Store interval data in Redis for API access
        """
        redis_key = f"ohlcv:{ohlcv_data.symbol}:{ohlcv_data.interval}:{ohlcv_data.timestamp.isoformat()}"
        
        data = {
            'symbol': ohlcv_data.symbol,
            'open': float(ohlcv_data.open),
            'high': float(ohlcv_data.high),
            'low': float(ohlcv_data.low),
            'close': float(ohlcv_data.close),
            'volume': ohlcv_data.volume,
            'timestamp': ohlcv_data.timestamp.isoformat(),
            'interval': ohlcv_data.interval
        }
        
        # TTL based on interval (longer intervals kept longer)
        ttl_hours = {
            '5m': 24,   # 1 day
            '15m': 72,  # 3 days
            '30m': 168, # 1 week
            '1h': 336,  # 2 weeks
            '4h': 720,  # 1 month
            '8h': 720   # 1 month
        }
        
        ttl_seconds = ttl_hours.get(ohlcv_data.interval, 24) * 3600
        await self.redis_client.setex(redis_key, ttl_seconds, json.dumps(data))
        
        # Also update "latest" key for each interval
        latest_key = f"latest:{ohlcv_data.symbol}:{ohlcv_data.interval}"
        await self.redis_client.setex(latest_key, ttl_seconds, json.dumps(data))
    
    async def send_to_kinesis(self, ohlcv_data: OHLCVData):
        """
        Send aggregated data to Kinesis for Aurora storage
        """
        try:
            await self.kinesis_client.put_record(
                data={
                    'record_type': 'aggregated_ohlcv',
                    'symbol': ohlcv_data.symbol,
                    'open': float(ohlcv_data.open),
                    'high': float(ohlcv_data.high),
                    'low': float(ohlcv_data.low),
                    'close': float(ohlcv_data.close),
                    'volume': ohlcv_data.volume,
                    'timestamp': ohlcv_data.timestamp.isoformat(),
                    'interval': ohlcv_data.interval,
                    'processed_at': datetime.utcnow().isoformat()
                },
                partition_key=f"{ohlcv_data.symbol}#{ohlcv_data.interval}"
            )
        except Exception as e:
            logger.error(f"Error sending {ohlcv_data.symbol} {ohlcv_data.interval} to Kinesis: {str(e)}")
    
    def get_interval_start(self, current_time: datetime, minutes: int) -> datetime:
        """
        Get the start of the current interval boundary
        
        Examples:
        - For 5m intervals: 10:17 -> 10:15, 10:23 -> 10:20
        - For 1h intervals: 10:45 -> 10:00
        """
        # Calculate minutes since midnight
        minutes_since_midnight = current_time.hour * 60 + current_time.minute
        
        # Round down to the nearest interval boundary
        interval_boundary = (minutes_since_midnight // minutes) * minutes
        
        # Create the interval start time
        interval_start = current_time.replace(
            hour=interval_boundary // 60,
            minute=interval_boundary % 60,
            second=0,
            microsecond=0
        )
        
        return interval_start
    
    async def get_active_symbols(self) -> List[str]:
        """
        Get active symbols from Redis or fallback list
        """
        try:
            # Try to get symbols that have recent tick data
            symbols = []
            
            # Look for symbols with recent activity (last 5 minutes)
            current_time = datetime.utcnow()
            lookback_time = current_time - timedelta(minutes=5)
            
            # This is a simple approach - in production you might maintain
            # a "active_symbols" set in Redis updated by the WebSocket handler
            default_symbols = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 
                'META', 'NVDA', 'NFLX', 'AMD', 'PYPL'
            ]
            
            return default_symbols
            
        except Exception as e:
            logger.error(f"Error getting active symbols: {str(e)}")
            return ['AAPL', 'MSFT', 'GOOGL']  # Minimal fallback

    async def placeholder_indicator_processing(self, ohlcv_data: OHLCVData):
        """
        PLACEHOLDER: Future indicator processing
        
        POST-MVP ENHANCEMENTS:
        - Consolidation detection across multiple timeframes
        - Support/resistance level calculation
        - Volume profile analysis
        - Trend analysis and breakout detection
        - Moving average calculations
        """
        # FUTURE: Detect consolidation patterns
        # consolidation_data = detect_consolidation(ohlcv_data)
        # if consolidation_data:
        #     await publish_consolidation_signal(consolidation_data)
        
        # FUTURE: Calculate pivot points
        # pivot_data = calculate_pivot_points(ohlcv_data)
        # if pivot_data:
        #     await publish_pivot_signals(pivot_data)
        
        # FUTURE: Volume analysis
        # volume_profile = analyze_volume_profile(ohlcv_data)
        # if volume_profile:
        #     await publish_volume_signals(volume_profile)
        
        logger.debug(f"Placeholder: Future indicator processing for {ohlcv_data.symbol} {ohlcv_data.interval}")


async def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for interval aggregation
    
    Triggered by EventBridge schedule every minute
    """
    aggregator = IntervalAggregator()
    
    try:
        # Get active symbols
        symbols = await aggregator.get_active_symbols()
        logger.info(f"Processing {len(symbols)} symbols for interval aggregation")
        
        # Process all intervals
        results = await aggregator.aggregate_intervals(symbols)
        
        # Summary logging
        total_records = sum(results.values())
        logger.info(f"Interval aggregation completed: {total_records} total records processed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Interval aggregation completed successfully',
                'symbols_processed': len(symbols),
                'intervals_processed': results,
                'total_records': total_records,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Error in interval aggregator: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }

# For local testing
if __name__ == "__main__":
    import asyncio
    
    # Mock event for testing
    test_event = {}
    
    class MockContext:
        def __init__(self):
            self.function_name = "test-interval-aggregator"
            self.function_version = "1"
    
    result = asyncio.run(lambda_handler(test_event, MockContext()))
    print(json.dumps(result, indent=2))