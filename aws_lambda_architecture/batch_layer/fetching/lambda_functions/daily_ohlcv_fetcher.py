"""
AWS Lambda function for daily OHLCV data fetching
Replaces the Prefect bronze pipeline with serverless AWS approach
Now with async support for 10x faster fetching!

NEW ARCHITECTURE:
1. Write to S3 bronze layer (SOURCE OF TRUTH, all historical data)
2. Write to RDS (FAST QUERY CACHE, last 5 years only)
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
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO
import pytz

# Import shared utilities (included in deployment package)
from shared.clients.polygon_client import PolygonClient
from shared.clients.rds_timescale_client import RDSPostgresClient
from shared.models.data_models import OHLCVData, BatchProcessingJob

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# S3 Configuration
S3_BUCKET = os.environ.get('S3_DATALAKE_BUCKET', 'dev-condvest-datalake')
S3_BRONZE_PREFIX = 'bronze/raw_ohlcv'


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for daily OHLCV data fetching
    
    Event can contain:
    - symbols: List of symbols to fetch (optional, defaults to all active)
    - date: Date to fetch data for (optional, defaults to previous trading day)
    - force: Boolean to force execution even on non-trading days
    - skip_market_check: Boolean to skip market status check (useful for testing)
    - backfill_missing: Boolean to auto-detect and fetch missing dates
    - max_backfill_days: Max number of days to backfill (default: 30)
    """
    
    try:
        # Parse event parameters (early)
        skip_market_check = event.get('skip_market_check', False)
        
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
        
        # Market Status Check (can be skipped for testing)
        if not skip_market_check:
            market_status = polygon_client.get_market_status()
            if market_status['market'] == 'closed':
                logger.info(f"Skipping execution - market is closed")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'Skipping execution - market is closed'})
                }
        else:
            logger.info("⚠️  TESTING MODE: Skipping market status check")
        
        # Parse remaining event parameters
        symbols = event.get('symbols', None)  # None means fetch all active symbols
        target_date = event.get('date', None)
        force_execution = event.get('force', False)
        backfill_missing = event.get('backfill_missing', True)  # Default: auto-detect missing dates
        max_backfill_days = int(event.get('max_backfill_days', 30))  # Limit backfill to last 30 days
        
        # 📊 LOG EXECUTION MODE (IMPORTANT FOR PRODUCTION VISIBILITY)
        execution_mode = "UNKNOWN"
        if target_date:
            execution_mode = "SPECIFIC_DATE"
        elif backfill_missing and max_backfill_days > 30:
            execution_mode = "LARGE_BACKFILL"  # Manual historical backfill
        elif backfill_missing:
            execution_mode = "PRODUCTION"  # Daily incremental with auto-recovery
        else:
            execution_mode = "SINGLE_DAY"
        
        logger.info(f"🚀 EXECUTION MODE: {execution_mode}")
        logger.info(f"📋 Event Parameters: backfill_missing={backfill_missing}, max_backfill_days={max_backfill_days}, skip_market_check={skip_market_check}")
        
        # Determine target date(s) to fetch
        dates_to_fetch = []
        if target_date:
            # Specific date requested
            target_date = datetime.fromisoformat(target_date).date()
            dates_to_fetch = [target_date]
            logger.info(f"📅 Specific date mode: {target_date}")
        elif backfill_missing:
            # Smart mode: find missing dates in database
            logger.info(f"🔍 Smart backfill mode: checking for missing dates (last {max_backfill_days} days)...")
            dates_to_fetch = get_missing_dates(rds_client, max_backfill_days)
            if not dates_to_fetch:
                logger.info("✅ No missing dates found - database is up to date!")
                logger.info(f"🎯 Mode: {execution_mode} - No action needed")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'No missing dates - database is up to date',
                        'execution_mode': execution_mode
                    })
                }
            logger.info(f"📅 Found {len(dates_to_fetch)} missing dates to backfill: {dates_to_fetch[0]} to {dates_to_fetch[-1]}")
        else:
            # Default: just fetch previous trading day
            target_date = polygon_client.get_previous_trading_day()
            dates_to_fetch = [target_date]
            logger.info(f"📅 Single day mode: {target_date}")
        
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
                        # NEW ARCHITECTURE: Write to S3 first (SOURCE OF TRUTH)
                        s3_records = write_to_s3_bronze(ohlcv_data, fetch_date)
                        logger.info(f"  ✅ Wrote {s3_records} records to S3 bronze layer")
                        
                        # Then write to RDS (FAST QUERY CACHE - last 5 years only)
                        records_inserted = write_to_rds_with_retention(
                            rds_client, 
                            ohlcv_data, 
                            retention_years=5
                        )
                        logger.info(f"  ✅ Inserted {records_inserted} records to RDS")
                        
                        # Extract symbols that actually returned data
                        symbols_with_data = list(set([ohlcv.symbol for ohlcv in ohlcv_data]))
                        logger.info(f"  📊 Data returned for {len(symbols_with_data)}/{len(batch_symbols)} symbols")
                        
                        # Update watermark ONLY for symbols that had data (CRITICAL FIX)
                        if symbols_with_data:
                            update_watermark(rds_client, symbols_with_data, fetch_date)
                        
                        date_records += records_inserted
                        total_records += records_inserted
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
        
        execution_time = (batch_job.end_time - batch_job.start_time).total_seconds()
        
        # Final summary with execution mode
        logger.info(f"✅ ========== JOB COMPLETE ==========")
        logger.info(f"🎯 Execution Mode: {execution_mode}")
        logger.info(f"📅 Dates Processed: {dates_to_fetch[0]} to {dates_to_fetch[-1]} ({len(dates_to_fetch)} dates)")
        logger.info(f"📊 Symbols: {len(symbols)} active symbols")
        logger.info(f"💾 Records Inserted: {total_records:,}")
        logger.info(f"⏱️  Execution Time: {execution_time:.1f}s")
        logger.info(f"🏁 Job ID: {job_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'OHLCV {execution_mode} completed successfully',
                'execution_mode': execution_mode,
                'job_id': job_id,
                'dates_processed': [d.isoformat() for d in dates_to_fetch],
                'num_dates': len(dates_to_fetch),
                'symbols_processed': len(symbols),
                'records_inserted': total_records,
                'execution_time_seconds': execution_time
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
    Find missing trading dates by checking watermark table (FAST & SCALABLE)
    
    INDUSTRY STANDARD APPROACH: Use metadata table (SCD Type 2) to track ingestion progress
    - Single SQL query vs scanning 480,000+ S3 files
    - Accurate per-symbol tracking with full history
    - Scalable to millions of symbols
    
    Args:
        rds_client: RDS client instance
        max_days_back: Maximum number of days to look back (default: 30)
    
    Returns:
        List of missing dates, sorted from oldest to newest
    """
    try:
        logger.info(f"🔍 Checking watermark table for missing dates...")
        
        # Query watermark table for latest ingested date (only current records)
        # If no data exists, start from max_days_back ago
        query = """
            SELECT 
                MAX(latest_date) as max_date, 
                MIN(latest_date) as min_date, 
                COUNT(DISTINCT symbol) as symbol_count
            FROM data_ingestion_watermark
            WHERE is_current = TRUE;
        """
        
        result = rds_client.execute_query(query)
        
        if not result or result[0]['max_date'] is None:
            # No data in watermark table - start fresh backfill
            logger.info(f"⚠️  No watermark data found, starting fresh backfill from {max_days_back} days ago")
            from_date = date.today() - timedelta(days=max_days_back)
        else:
            max_date = result[0]['max_date']
            symbol_count = result[0]['symbol_count']
            logger.info(f"✅ Found watermark: {symbol_count} symbols, latest date: {max_date}")
            from_date = max_date + timedelta(days=1)  # Start from day after latest
        
        # Determine latest available date based on market close time
        # Market closes at 4:00 PM ET, data becomes available shortly after
        eastern = pytz.timezone('US/Eastern')
        now_et = datetime.now(eastern)
        market_close_today = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # If after 4 PM ET on a weekday, today's data is available
        # Otherwise, fetch up to yesterday
        if now_et >= market_close_today and now_et.weekday() < 5:
            # Market closed today (weekday), today's data is available
            latest_available_date = date.today()
            logger.info(f"📊 Market closed today at 4 PM ET, fetching up to: {latest_available_date}")
        else:
            # Market hasn't closed yet, or it's weekend
            latest_available_date = date.today() - timedelta(days=1)
            if now_et.weekday() >= 5:
                logger.info(f"📅 Weekend - fetching up to: {latest_available_date}")
            else:
                logger.info(f"⏰ Before market close (4 PM ET) - fetching up to: {latest_available_date}")
        
        if from_date > latest_available_date:
            logger.info(f"✅ Data is up to date (latest: {from_date - timedelta(days=1)})")
            return []
        
        # Find missing dates (only trading days - weekdays)
        missing_dates = []
        current_date = from_date
        while current_date <= latest_available_date:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5:
                missing_dates.append(current_date)
            current_date += timedelta(days=1)
        
        # Limit to max_days_back most recent missing dates
        if len(missing_dates) > max_days_back:
            logger.warning(f"Found {len(missing_dates)} missing dates, limiting to {max_days_back} most recent")
            missing_dates = missing_dates[-max_days_back:]
        
        logger.info(f"📋 Missing dates to fetch: {len(missing_dates)}")
        
        return missing_dates
        
    except Exception as e:
        logger.error(f"❌ Error querying watermark table: {str(e)}")
        logger.warning("⚠️  Falling back to latest available date based on market time")
        
        # Fallback: Use same market timing logic
        eastern = pytz.timezone('US/Eastern')
        now_et = datetime.now(eastern)
        market_close_today = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        if now_et >= market_close_today and now_et.weekday() < 5:
            fallback_date = date.today()
        else:
            fallback_date = date.today() - timedelta(days=1)
        
        logger.info(f"📅 Fallback date: {fallback_date}")
        return [fallback_date] if fallback_date.weekday() < 5 else []


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


def write_to_s3_bronze(ohlcv_data: List[OHLCVData], fetch_date: date) -> int:
    """
    Write OHLCV data to S3 bronze layer (SOURCE OF TRUTH)
    
    Partitioning strategy: By symbol
    Path format: s3://bucket/bronze/raw_ohlcv/symbol=AAPL/date=2025-10-18.parquet
    
    Args:
        ohlcv_data: List of OHLCV data objects
        fetch_date: Date for which data was fetched
    
    Returns:
        Number of records written
    """
    if not ohlcv_data:
        return 0
    
    try:
        s3_client = boto3.client('s3')
        
        # Convert OHLCV data to DataFrame
        # Group data by symbol for partitioning (pure Python, no pandas!)
        symbol_groups = {}
        for ohlcv in ohlcv_data:
            if ohlcv.symbol not in symbol_groups:
                symbol_groups[ohlcv.symbol] = []
            symbol_groups[ohlcv.symbol].append(ohlcv)
        
        # Write each symbol's data to S3 as parquet
        records_written = 0
        for symbol, symbol_data in symbol_groups.items():
            # S3 key: bronze/raw_ohlcv/symbol=AAPL/date=2025-10-18.parquet
            s3_key = f"{S3_BRONZE_PREFIX}/symbol={symbol}/date={fetch_date.isoformat()}.parquet"
            
            # Convert to PyArrow Table directly (no pandas!)
            # Create arrays for each column
            table = pa.table({
                'symbol': [ohlcv.symbol for ohlcv in symbol_data],
                'open': [float(ohlcv.open) for ohlcv in symbol_data],
                'high': [float(ohlcv.high) for ohlcv in symbol_data],
                'low': [float(ohlcv.low) for ohlcv in symbol_data],
                'close': [float(ohlcv.close) for ohlcv in symbol_data],
                'volume': [int(ohlcv.volume) for ohlcv in symbol_data],
                'timestamp': [ohlcv.timestamp for ohlcv in symbol_data],
                'interval': [ohlcv.interval for ohlcv in symbol_data]
            })
            
            # Write to parquet in memory
            parquet_buffer = BytesIO()
            pq.write_table(table, parquet_buffer, compression='snappy')
            parquet_buffer.seek(0)
            
            # Check if file already exists (deduplication)
            try:
                s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
                logger.info(f"  ⚠️  File already exists, overwriting: s3://{S3_BUCKET}/{s3_key}")
            except:
                pass  # File doesn't exist, continue
            
            # Write to S3
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=parquet_buffer.getvalue(),
                ContentType='application/x-parquet'
            )
            
            records_written += len(symbol_data)
            logger.debug(f"  📦 Wrote {len(symbol_data)} records for {symbol} to S3")
        
        logger.info(f"✅ Successfully wrote {records_written} records to S3 bronze layer")
        logger.info(f"   Location: s3://{S3_BUCKET}/{S3_BRONZE_PREFIX}/")
        
        return records_written
        
    except Exception as e:
        logger.error(f"❌ Error writing to S3 bronze layer: {str(e)}")
        raise  # Re-raise to fail the Lambda if S3 write fails (critical)


def write_to_rds_with_retention(
    rds_client: RDSPostgresClient, 
    ohlcv_data: List[OHLCVData],
    retention_years: int = 5
) -> int:
    """
    Write OHLCV data to RDS with retention policy (FAST QUERY CACHE)
    Only keeps last N years of data in RDS for fast queries
    
    NOTE: Weekly archival procedure (archive_old_ohlcv_data) handles cleanup
    This function just inserts data normally, archival runs separately
    
    Args:
        rds_client: RDS client instance
        ohlcv_data: List of OHLCV data objects
        retention_years: Number of years to keep in RDS (default: 5)
    
    Returns:
        Number of records inserted
    """
    if not ohlcv_data:
        return 0
    
    try:
        # Filter out data older than retention period (shouldn't happen for daily fetcher)
        retention_threshold = date.today() - timedelta(days=365 * retention_years + 30)  # +1 month buffer
        
        filtered_data = [
            ohlcv for ohlcv in ohlcv_data 
            if ohlcv.timestamp.date() >= retention_threshold
        ]
        
        if len(filtered_data) < len(ohlcv_data):
            logger.warning(
                f"⚠️  Filtered out {len(ohlcv_data) - len(filtered_data)} records "
                f"older than {retention_threshold} (outside retention period)"
            )
        
        if not filtered_data:
            logger.info("ℹ️  No records within retention period, skipping RDS insert")
            return 0
        
        # Insert to RDS (uses UPSERT internally to handle duplicates)
        records_inserted = rds_client.insert_ohlcv_data(filtered_data)
        
        logger.info(f"✅ Inserted {records_inserted} records to RDS (retention: {retention_years} years)")
        
        return records_inserted
        
    except Exception as e:
        logger.error(f"❌ Error writing to RDS: {str(e)}")
        # Don't fail Lambda if RDS write fails (S3 is source of truth)
        # But log it prominently for monitoring
        logger.error("⚠️  RDS write failed, but S3 write succeeded (data not lost)")
        return 0


def update_watermark(rds_client: RDSPostgresClient, symbols: List[str], fetch_date: date):
    """
    Update watermark table after successful ingestion (SCD TYPE 2 PATTERN)
    
    SCD Type 2 Implementation:
    1. Mark old record as is_current = FALSE (keep history)
    2. Insert new record with is_current = TRUE (new current)
    
    This provides full audit trail while keeping fast lookups
    
    Args:
        rds_client: RDS client instance
        symbols: List of symbols that were successfully ingested
        fetch_date: Date that was ingested
    """
    try:
        # Access connection directly from client
        conn = rds_client.connection
        cursor = conn.cursor()
        
        # Temporarily disable autocommit for transaction
        old_autocommit = conn.autocommit
        conn.autocommit = False
        
        try:
            for symbol in symbols:
                # Step 1: Mark old record as not current (SCD Type 2)
                update_query = """
                    UPDATE data_ingestion_watermark
                    SET is_current = FALSE
                    WHERE symbol = %s AND is_current = TRUE;
                """
                cursor.execute(update_query, (symbol,))
                
                # Step 2: Insert new current record
                insert_query = """
                    INSERT INTO data_ingestion_watermark 
                        (symbol, latest_date, ingested_at, records_count, is_current)
                    VALUES (%s, %s, NOW(), 1, TRUE);
                """
                cursor.execute(insert_query, (symbol, fetch_date))
            
            conn.commit()
            logger.info(f"✅ Updated watermark for {len(symbols)} symbols (date: {fetch_date}, SCD Type 2)")
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.autocommit = old_autocommit
        
    except Exception as e:
        logger.error(f"❌ Error updating watermark: {str(e)}")
        # Don't fail Lambda for watermark update failures
        # Worst case: we re-process some data next run (idempotent)
