"""
AWS Lambda function for daily OHLCV data fetching
Replaces the Prefect bronze pipeline with serverless AWS approach
"""

import json
import boto3
import psycopg2
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import os
from decimal import Decimal

# Import shared utilities (we'll create these)
import sys
sys.path.append('/opt/python')  # Lambda layer path
from shared.clients.polygon_client import PolygonClient
from shared.clients.aurora_client import AuroraClient
from shared.models.data_models import OHLCVData, BatchProcessingJob
from shared.utils.market_calendar import is_trading_day

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
        # Initialize clients
        polygon_client = PolygonClient(api_key=os.environ['POLYGON_API_KEY'])
        aurora_client = AuroraClient(
            cluster_arn=os.environ['AURORA_CLUSTER_ARN'],
            secret_arn=os.environ['AURORA_SECRET_ARN'],
            database_name=os.environ['DATABASE_NAME']
        ) 
        
        # Parse event parameters
        symbols = event.get('symbols', None)  # None means fetch all active symbols
        target_date = event.get('date', None)
        force_execution = event.get('force', False)
        
        # Determine target date
        if target_date:
            target_date = datetime.fromisoformat(target_date).date()
        else:
            target_date = get_previous_trading_day()
        
        # Check if we should run
        if not force_execution and not is_trading_day(target_date):
            logger.info(f"Skipping execution - {target_date} is not a trading day")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Skipped - {target_date} is not a trading day',
                    'date': target_date.isoformat()
                })
            }
        
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
            symbols = aurora_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from database")
        
        batch_job.symbols_processed = symbols
        
        # Process symbols in batches
        batch_size = int(os.environ.get('BATCH_SIZE', '50'))
        total_records = 0
        
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_symbols)} symbols")
            
            try:
                # Fetch OHLCV data for batch
                ohlcv_data = polygon_client.fetch_batch_ohlcv_data(batch_symbols, target_date)
                
                if ohlcv_data:
                    # Store in Aurora
                    records_inserted = aurora_client.insert_ohlcv_data(ohlcv_data)
                    total_records += records_inserted
                    
                    logger.info(f"Inserted {records_inserted} records for batch")
                else:
                    logger.warning(f"No data returned for batch: {batch_symbols}")
                    
            except Exception as e:
                logger.error(f"Error processing batch {batch_symbols}: {str(e)}")
                # Continue with next batch rather than failing entire job
                continue
        
        # Update job status
        batch_job.status = 'COMPLETED'
        batch_job.end_time = datetime.utcnow()
        batch_job.records_processed = total_records
        
        # Store job metadata (optional - for monitoring)
        store_job_metadata(aurora_client, batch_job)
        
        # Trigger downstream processing (Silver layer)
        trigger_silver_layer_processing(target_date)
        
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
            store_job_metadata(aurora_client, batch_job)
        
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

def get_previous_trading_day() -> datetime.date:
    """
    Get the previous trading day
    """
    today = datetime.now().date()
    days_back = 1
    
    while days_back <= 7:  # Don't go back more than a week
        check_date = today - timedelta(days=days_back)
        if is_trading_day(check_date):
            return check_date
        days_back += 1
    
    # Fallback to yesterday if no trading day found
    return today - timedelta(days=1)

def store_job_metadata(aurora_client: AuroraClient, batch_job: BatchProcessingJob):
    """
    Store batch job metadata for monitoring
    """
    try:
        aurora_client.insert_batch_job_metadata(batch_job)
    except Exception as e:
        logger.error(f"Error storing job metadata: {str(e)}")
        # Don't fail the main job for metadata storage issues

def trigger_silver_layer_processing(target_date: datetime.date):
    """
    Trigger the Silver layer processing after Bronze layer completion
    """
    try:
        lambda_client = boto3.client('lambda')
        
        # Invoke Silver layer Lambda asynchronously
        response = lambda_client.invoke(
            FunctionName=os.environ['SILVER_LAYER_FUNCTION_NAME'],
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps({
                'date': target_date.isoformat(),
                'triggered_by': 'bronze_layer'
            })
        )
        
        logger.info(f"Triggered Silver layer processing for {target_date}")
        
    except Exception as e:
        logger.error(f"Error triggering Silver layer: {str(e)}")
        # Don't fail Bronze layer for Silver layer trigger issues
