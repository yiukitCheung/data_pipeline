"""
AWS Lambda function for daily OHLCV data fetching
Replaces the Prefect bronze pipeline with serverless AWS approach
Now with async support for 10x faster fetching!
"""

import json
import boto3
import psycopg2
import logging
import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import os
from decimal import Decimal

# Import shared utilities (included in deployment package)
from shared.clients.polygon_client import PolygonClient
from shared.clients.rds_timescale_client import RDSTimescaleClient
from shared.models.data_models import OHLCVData, BatchProcessingJob

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for daily OHLCV data fetching
    
    Event can contain:
    - symbols: List of symbols to fetch (optional, defaults to all active)
    - date: Date to fetch data for (optional, defaults to previous trading day)
    - force: Boolean to force execution even on non-trading days
    """
    
    try:
        # Get Polygon API key from Secrets Manager
        secrets_client = boto3.client('secretsmanager')
        polygon_secret = secrets_client.get_secret_value(
            SecretId=os.environ['POLYGON_API_KEY_SECRET_ARN']
        )
        polygon_api_key = json.loads(polygon_secret['SecretString'])['POLYGON_API_KEY']
        
        # Initialize clients
        polygon_client = PolygonClient(api_key=polygon_api_key)
        rds_client = RDSTimescaleClient(
            secret_arn=os.environ['RDS_SECRET_ARN']
        ) 
        # Market Status
        market_status = polygon_client.get_market_status()
        if market_status['market'] == 'closed':
            logger.info(f"Skipping execution - market is closed")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Skipping execution - market is closed'})
            }
        # Parse event parameters
        symbols = event.get('symbols', None)  # None means fetch all active symbols
        target_date = event.get('date', None)
        force_execution = event.get('force', False)
        
        # Determine target date
        if target_date:
            target_date = datetime.fromisoformat(target_date).date()
        else:
            target_date = polygon_client.get_previous_trading_day()
        
        # Create batch job record
        job_id = f"daily-ohlcv-{target_date.isoformat()}-{int(datetime.utcnow().timestamp())}"
        batch_job = BatchProcessingJob(
            job_id=job_id,
            job_type='DAILY_OHLCV',
            status='RUNNING',
            start_time=datetime.utcnow(),
            symbols_processed=[],
            records_processed=0
        )
        
        logger.info(f"Starting daily OHLCV fetch for {target_date}, job_id: {job_id}")
        
        # Get symbols to process
        if symbols is None:
            symbols = rds_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from RDS TimescaleDB")
        
        batch_job.symbols_processed = symbols
        
        # Process symbols in batches
        batch_size = int(os.environ.get('BATCH_SIZE', '50'))
        total_records = 0
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_symbols)} symbols (async)")
            
            try:
                # Fetch OHLCV data for batch ASYNC (10x faster!)
                ohlcv_data = asyncio.run(
                    polygon_client.fetch_batch_ohlcv_data_async(
                        batch_symbols, 
                        target_date,
                        max_concurrent=10  # Concurrent requests
                    )
                )
                
                if ohlcv_data:
                    # Store in RDS TimescaleDB
                    records_inserted = rds_client.insert_ohlcv_data(ohlcv_data)
                    total_records += records_inserted
                    
                    logger.info(f"Inserted {records_inserted} records for batch (async fetch)")
                else:
                    logger.warning(f"No data returned for batch: {batch_symbols[:5]}...")
            except Exception as e:  
                logger.error(f"Error processing batch: {str(e)}")
                # Continue with next batch rather than failing entire job
                continue
        
        # Update job status
        batch_job.status = 'COMPLETED'
        batch_job.end_time = datetime.utcnow()
        batch_job.records_processed = total_records
        
        # Store job metadata (optional - for monitoring)
        store_job_metadata(rds_client, batch_job)
        
        # Trigger downstream processing (Silver layer - Fibonacci resampling)
        trigger_fibonacci_resampling_job(target_date)
        
        logger.info(f"Completed daily OHLCV fetch. Total records: {total_records}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Daily OHLCV fetch completed successfully',
                'job_id': job_id,
                'date': target_date.isoformat(),
                'symbols_processed': len(symbols),
                'records_inserted': total_records,
                'execution_time_seconds': (batch_job.end_time - batch_job.start_time).total_seconds()
            })
        }
        
    except Exception as e:
        logger.error(f"Fatal error in daily OHLCV fetcher: {str(e)}")
        
        # Update job status to failed
        if 'batch_job' in locals():
            batch_job.status = 'FAILED'
            batch_job.end_time = datetime.utcnow()
            batch_job.error_message = str(e)
            store_job_metadata(rds_client, batch_job)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Daily OHLCV fetch failed',
                'message': str(e)
            })
        }

# Fix line 98-104: Replace the fetch_ohlcv_batch function with proven logic
def fetch_ohlcv_batch(
    polygon_client: PolygonClient, 
    symbols: List[str], 
    target_date: date
) -> List[OHLCVData]:
    """
    Fetch OHLCV data for a batch of symbols - using proven method
    """
    # Use the proven batch method from our tests
    return polygon_client.fetch_batch_ohlcv_data(symbols, target_date)


def store_job_metadata(rds_client: RDSTimescaleClient, batch_job: BatchProcessingJob):
    """
    Store batch job metadata for monitoring
    """
    try:
        rds_client.insert_batch_job_metadata(batch_job)
    except Exception as e:
        logger.error(f"Error storing job metadata: {str(e)}")
        # Don't fail the main job for metadata storage issues

def trigger_fibonacci_resampling_job(target_date: datetime.date):
    """
    Trigger the S3 Data Lake Resampling job after bronze layer completion
    Uses AWS Batch for cost-efficient DuckDB + S3 processing
    """
    try:
        batch_client = boto3.client('batch')
        
        # Submit S3 Data Lake Resampling job to AWS Batch
        job_name = f"s3-resampler-{target_date.isoformat()}-{int(datetime.utcnow().timestamp())}"
        
        response = batch_client.submit_job(
            jobName=job_name,
            jobQueue=os.environ.get('BATCH_JOB_QUEUE', 'dev-batch-duckdb-resampler'),
            jobDefinition=os.environ.get('RESAMPLING_JOB_DEFINITION', 'dev-batch-duckdb-resampler')
        )
        
        job_id = response['jobId']
        logger.info(f"✅ Triggered S3 Data Lake Resampling job {job_name} (ID: {job_id}) for {target_date}")
        logger.info(f"📦 Resampler will write silver data to S3: s3://dev-condvest-datalake/silver/")
        
        return job_id
        
    except Exception as e:
        logger.error(f"❌ Error triggering S3 Resampling job: {str(e)}")
        # Don't fail Bronze layer for Resampling layer trigger issues
        return None
