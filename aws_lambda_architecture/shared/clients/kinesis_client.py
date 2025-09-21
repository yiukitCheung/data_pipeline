"""
AWS Kinesis Data Streams Client for Speed Layer

Handles real-time data streaming to Kinesis for signal processing.
Used by ECS WebSocket service and Lambda functions.
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional, Union
from datetime import datetime
import uuid

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)

class KinesisClient:
    """
    AWS Kinesis Data Streams client for real-time data ingestion
    
    Features:
    - Async/sync put_record methods
    - Automatic JSON serialization
    - Error handling and retries
    - Batch operations support
    - Partition key management
    """
    
    def __init__(self, stream_name: str, region_name: str = 'us-east-1'):
        """
        Initialize Kinesis client
        
        Args:
            stream_name: Name of the Kinesis stream
            region_name: AWS region (default: us-east-1)
        """
        self.stream_name = stream_name
        self.region_name = region_name
        
        # Initialize boto3 client
        try:
            self.kinesis_client = boto3.client('kinesis', region_name=region_name)
            logger.info(f"Kinesis client initialized for stream: {stream_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Kinesis client: {str(e)}")
            raise
    
    async def put_record(
        self, 
        data: Union[Dict[str, Any], str], 
        partition_key: str,
        sequence_number_for_ordering: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Put a single record to Kinesis stream (async)
        
        Args:
            data: Data to send (dict will be JSON serialized)
            partition_key: Partition key for data distribution
            sequence_number_for_ordering: Optional sequence number for ordering
            
        Returns:
            Kinesis response dict with ShardId and SequenceNumber
        """
        try:
            # Serialize data if it's a dict
            if isinstance(data, dict):
                data_bytes = json.dumps(data, default=str).encode('utf-8')
            else:
                data_bytes = str(data).encode('utf-8')
            
            # Prepare put_record parameters
            put_params = {
                'StreamName': self.stream_name,
                'Data': data_bytes,
                'PartitionKey': partition_key
            }
            
            if sequence_number_for_ordering:
                put_params['SequenceNumberForOrdering'] = sequence_number_for_ordering
            
            # Execute in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.kinesis_client.put_record(**put_params)
            )
            
            logger.debug(f"Successfully sent record to {self.stream_name}, "
                        f"shard: {response['ShardId']}, "
                        f"sequence: {response['SequenceNumber']}")
            
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Kinesis ClientError [{error_code}]: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Kinesis put_record error: {str(e)}")
            raise
    
    def put_record_sync(
        self, 
        data: Union[Dict[str, Any], str], 
        partition_key: str,
        sequence_number_for_ordering: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Put a single record to Kinesis stream (synchronous)
        
        Args:
            data: Data to send (dict will be JSON serialized)
            partition_key: Partition key for data distribution
            sequence_number_for_ordering: Optional sequence number for ordering
            
        Returns:
            Kinesis response dict with ShardId and SequenceNumber
        """
        try:
            # Serialize data if it's a dict
            if isinstance(data, dict):
                data_bytes = json.dumps(data, default=str).encode('utf-8')
            else:
                data_bytes = str(data).encode('utf-8')
            
            # Prepare put_record parameters
            put_params = {
                'StreamName': self.stream_name,
                'Data': data_bytes,
                'PartitionKey': partition_key
            }
            
            if sequence_number_for_ordering:
                put_params['SequenceNumberForOrdering'] = sequence_number_for_ordering
            
            response = self.kinesis_client.put_record(**put_params)
            
            logger.debug(f"Successfully sent record to {self.stream_name}, "
                        f"shard: {response['ShardId']}, "
                        f"sequence: {response['SequenceNumber']}")
            
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Kinesis ClientError [{error_code}]: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Kinesis put_record_sync error: {str(e)}")
            raise
    
    async def put_records_batch(
        self, 
        records: list[Dict[str, Any]], 
        default_partition_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Put multiple records to Kinesis stream in batch (async)
        
        Args:
            records: List of record dicts with 'data' and optional 'partition_key'
            default_partition_key: Default partition key if not specified per record
            
        Returns:
            Kinesis batch response with FailedRecordCount and Records
        """
        try:
            # Prepare batch records
            batch_records = []
            
            for i, record in enumerate(records):
                # Get data and partition key
                data = record.get('data')
                partition_key = record.get('partition_key', default_partition_key)
                
                if not partition_key:
                    partition_key = str(uuid.uuid4())  # Generate random if missing
                
                # Serialize data
                if isinstance(data, dict):
                    data_bytes = json.dumps(data, default=str).encode('utf-8')
                else:
                    data_bytes = str(data).encode('utf-8')
                
                batch_records.append({
                    'Data': data_bytes,
                    'PartitionKey': partition_key
                })
            
            # Execute in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.kinesis_client.put_records(
                    StreamName=self.stream_name,
                    Records=batch_records
                )
            )
            
            # Log results
            failed_count = response.get('FailedRecordCount', 0)
            success_count = len(batch_records) - failed_count
            
            logger.info(f"Batch put_records: {success_count} success, {failed_count} failed")
            
            if failed_count > 0:
                logger.warning(f"Failed records in batch: {failed_count}")
                for i, record in enumerate(response.get('Records', [])):
                    if 'ErrorCode' in record:
                        logger.warning(f"Record {i} failed: {record['ErrorCode']} - {record.get('ErrorMessage', '')}")
            
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Kinesis batch ClientError [{error_code}]: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Kinesis put_records_batch error: {str(e)}")
            raise
    
    async def get_stream_description(self) -> Dict[str, Any]:
        """
        Get Kinesis stream description (async)
        
        Returns:
            Stream description with status, shards, etc.
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.kinesis_client.describe_stream(StreamName=self.stream_name)
            )
            
            stream_description = response['StreamDescription']
            logger.info(f"Stream {self.stream_name} status: {stream_description['StreamStatus']}")
            logger.info(f"Shard count: {len(stream_description.get('Shards', []))}")
            
            return stream_description
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Kinesis describe_stream ClientError [{error_code}]: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Kinesis get_stream_description error: {str(e)}")
            raise
    
    def create_ohlcv_record(
        self, 
        symbol: str, 
        open_price: float, 
        high_price: float, 
        low_price: float, 
        close_price: float,
        volume: int,
        timestamp: datetime,
        interval: str = '1m',
        source: str = 'websocket'
    ) -> Dict[str, Any]:
        """
        Create a standardized OHLCV record for Kinesis
        
        Args:
            symbol: Stock symbol
            open_price, high_price, low_price, close_price: OHLC prices
            volume: Trading volume
            timestamp: Data timestamp
            interval: Time interval (1m, 5m, etc.)
            source: Data source identifier
            
        Returns:
            Standardized OHLCV record dict
        """
        return {
            'record_type': 'ohlcv',
            'symbol': symbol,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
            'timestamp': timestamp.isoformat(),
            'interval': interval,
            'source': source,
            'ingestion_time': datetime.utcnow().isoformat()
        }
    
    def create_signal_record(
        self,
        symbol: str,
        signal_type: str,
        signal_value: Union[float, str, bool],
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a standardized signal record for Kinesis
        
        Args:
            symbol: Stock symbol
            signal_type: Type of signal (e.g., 'breakout', 'momentum', 'volume_spike')
            signal_value: Signal value (price level, direction, etc.)
            confidence: Signal confidence (0.0 to 1.0)
            metadata: Additional signal metadata
            
        Returns:
            Standardized signal record dict
        """
        return {
            'record_type': 'signal',
            'symbol': symbol,
            'signal_type': signal_type,
            'signal_value': signal_value,
            'confidence': confidence,
            'metadata': metadata or {},
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'speed_layer'
        }
    
    async def close(self):
        """
        Close the Kinesis client (cleanup)
        """
        # boto3 clients don't need explicit closing, but we can log
        logger.info(f"Kinesis client for {self.stream_name} closed")
