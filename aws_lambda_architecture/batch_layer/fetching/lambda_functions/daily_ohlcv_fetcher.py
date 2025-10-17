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
from shared.clients.rds_timescale_client import RDSPostgresClient
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
        rds_client = RDSPostgresClient(
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
        backfill_missing = event.get('backfill_missing', True)  # Default: auto-detect missing dates
        max_backfill_days = int(event.get('max_backfill_days', 30))  # Limit backfill to last 30 days
        
        # Determine target date(s) to fetch
        dates_to_fetch = []
        if target_date:
            # Specific date requested
            target_date = datetime.fromisoformat(target_date).date()
            dates_to_fetch = [target_date]
        elif backfill_missing:
            # Smart mode: find missing dates in database
            logger.info("🔍 Smart backfill mode: checking for missing dates...")
            dates_to_fetch = get_missing_dates(rds_client, max_backfill_days)
            if not dates_to_fetch:
                logger.info("✅ No missing dates found - database is up to date!")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'No missing dates - database is up to date'})
                }
            logger.info(f"📅 Found {len(dates_to_fetch)} missing dates to backfill: {[d.isoformat() for d in dates_to_fetch]}")
        else:
            # Default: just fetch previous trading day
            target_date = polygon_client.get_previous_trading_day()
            dates_to_fetch = [target_date]
        
        # Create batch job record
        job_id = f"daily-ohlcv-backfill-{int(datetime.utcnow().timestamp())}"
        batch_job = BatchProcessingJob(
            job_id=job_id,
            job_type='DAILY_OHLCV',
            status='RUNNING',
            start_time=datetime.utcnow(),
            symbols_processed=[],
            records_processed=0
        )
        
        logger.info(f"Starting OHLCV fetch for {len(dates_to_fetch)} date(s), job_id: {job_id}")
        
        # Get symbols to process
        if symbols is None:
            symbols = rds_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from RDS TimescaleDB")
        
        batch_job.symbols_processed = symbols
        
        # Process each date
        batch_size = int(os.environ.get('BATCH_SIZE', '50'))
        total_records = 0
        
        for date_idx, fetch_date in enumerate(dates_to_fetch, 1):
            logger.info(f"📅 Processing date {date_idx}/{len(dates_to_fetch)}: {fetch_date.isoformat()}")
            date_records = 0
            
            # Process symbols in batches for this date
            for i in range(0, len(symbols), batch_size):
                batch_symbols = symbols[i:i + batch_size]
                logger.info(f"  Batch {i//batch_size + 1}: {len(batch_symbols)} symbols (async)")
                
                try:
                    # Fetch OHLCV data for batch ASYNC (10x faster!)
                    ohlcv_data = asyncio.run(
                        polygon_client.fetch_batch_ohlcv_data_async(
                            batch_symbols, 
                            fetch_date,
                            max_concurrent=10  # Concurrent requests
                        )
                    )
                    
                    if ohlcv_data:
                        # Store in RDS TimescaleDB
                        records_inserted = rds_client.insert_ohlcv_data(ohlcv_data)
                        date_records += records_inserted
                        total_records += records_inserted
                        
                        logger.info(f"  Inserted {records_inserted} records for batch")
                    else:
                        logger.warning(f"  No data returned for batch: {batch_symbols[:5]}...")
                except Exception as e:  
                    logger.error(f"  Error processing batch: {str(e)}")
                    # Continue with next batch rather than failing entire job
                    continue
            
            logger.info(f"✅ Completed {fetch_date.isoformat()}: {date_records} records")
        
        # Update job status
        batch_job.status = 'COMPLETED'
        batch_job.end_time = datetime.utcnow()
        batch_job.records_processed = total_records
        
        # Store job metadata (optional - for monitoring)
        store_job_metadata(rds_client, batch_job)
        
        # Trigger downstream processing (Silver layer - Fibonacci resampling) for the latest date
        latest_date = max(dates_to_fetch) if dates_to_fetch else None
        if latest_date:
            trigger_fibonacci_resampling_job(latest_date)
        
        logger.info(f"Completed OHLCV backfill. Total records: {total_records} across {len(dates_to_fetch)} dates")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'OHLCV backfill completed successfully',
                'job_id': job_id,
                'dates_processed': [d.isoformat() for d in dates_to_fetch],
                'num_dates': len(dates_to_fetch),
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

def get_missing_dates(rds_client: RDSPostgresClient, max_days_back: int = 30) -> List[date]:
    """
    Find missing trading dates in the database
    
    Args:
        rds_client: RDS client instance
        max_days_back: Maximum number of days to look back (default: 30)
    
    Returns:
        List of missing dates, sorted from oldest to newest
    """
    try:
        # Get the latest date in database
        query = """
        SELECT MAX(DATE(timestamp)) as latest_date 
        FROM bronze_ohlcv
        """
        result = rds_client.execute_query(query)
        
        if not result or not result[0]['latest_date']:
            # No data in database - start from 30 days ago
            logger.info("No data found in database, starting backfill from scratch")
            from_date = date.today() - timedelta(days=max_days_back)
        else:
            latest_date = result[0]['latest_date']
            if isinstance(latest_date, str):
                latest_date = datetime.fromisoformat(latest_date).date()
            from_date = latest_date + timedelta(days=1)  # Start from day after latest
        
        # Get all trading days from from_date to yesterday
        yesterday = date.today() - timedelta(days=1)
        
        if from_date > yesterday:
            logger.info(f"Database is up to date (latest: {from_date - timedelta(days=1)})")
            return []
        
        # Get actual dates that exist in database for this period
        query = f"""
        SELECT DISTINCT DATE(timestamp) as trade_date 
        FROM bronze_ohlcv
        WHERE DATE(timestamp) BETWEEN '{from_date.isoformat()}' AND '{yesterday.isoformat()}'
        ORDER BY trade_date
        """
        result = rds_client.execute_query(query)
        existing_dates = set()
        if result:
            for row in result:
                trade_date = row['trade_date']
                if isinstance(trade_date, str):
                    trade_date = datetime.fromisoformat(trade_date).date()
                existing_dates.add(trade_date)
        
        # Find missing dates (only trading days - weekdays)
        missing_dates = []
        current_date = from_date
        while current_date <= yesterday:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5 and current_date not in existing_dates:
                missing_dates.append(current_date)
            current_date += timedelta(days=1)
        
        # Limit to max_days_back most recent missing dates
        if len(missing_dates) > max_days_back:
            logger.warning(f"Found {len(missing_dates)} missing dates, limiting to {max_days_back} most recent")
            missing_dates = missing_dates[-max_days_back:]
        
        return missing_dates
        
    except Exception as e:
        logger.error(f"Error detecting missing dates: {str(e)}")
        # Fallback: just return yesterday
        return [date.today() - timedelta(days=1)]


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


def store_job_metadata(rds_client: RDSPostgresClient, batch_job: BatchProcessingJob):
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
