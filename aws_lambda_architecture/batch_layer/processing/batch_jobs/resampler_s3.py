"""
Optimized OHLCV Resampler using DuckDB + S3 (Pure Data Lake Architecture)
Purpose: High-performance resampling using DuckDB for S3 data processing

Cost-efficient data lake approach that leverages:
- DuckDB for fast S3 data reading and resampling
- S3 for scalable data storage (Bronze → Silver layers)
- Parquet format for efficient analytics queries
- No RDS dependency - pure S3-based data lake
Uses proven ROW_NUMBER windowing approach optimized for DuckDB.
"""

import os
import sys
import logging
import time
import duckdb
import pandas as pd
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
import boto3
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DuckDBS3Resampler:
    """
    High-performance OHLCV resampling using DuckDB + S3 (Pure Data Lake)
    
    Leverages:
    - DuckDB for fast S3 data reading and resampling
    - S3 for scalable data storage (Bronze → Silver)
    - Parquet format for efficient analytics
    - No RDS dependency - pure S3-based data lake
    - Proven ROW_NUMBER approach optimized for DuckDB
    """
    
    # Fibonacci intervals 3-34 (matching your settings.yaml)
    RESAMPLING_INTERVALS = [3, 5, 8, 13, 21, 34]
    
    def __init__(self, s3_bucket: str, s3_output_prefix: str = "silver"):
        """Initialize DuckDB connection and S3 configuration"""
        # Initialize DuckDB connection
        self.duckdb_conn = duckdb.connect()
        
        # S3 configuration
        self.s3_bucket = s3_bucket
        self.s3_output_prefix = s3_output_prefix
        self.s3_client = boto3.client('s3')
        
        # Configure DuckDB for S3 access
        self._setup_duckdb_s3_config()
        
        logger.info(f"DuckDB + S3 Data Lake Resampler initialized")
        logger.info(f"Output: s3://{s3_bucket}/{s3_output_prefix}/")
    
    def _setup_duckdb_s3_config(self):
        """Configure DuckDB for S3 access using IAM roles (AWS best practice)"""
        try:
            # Install and load the httpfs extension for S3 access
            self.duckdb_conn.execute("INSTALL httpfs")
            self.duckdb_conn.execute("LOAD httpfs")
            
            # Get AWS credentials from the environment (ECS task IAM role)
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials:
                # Use temporary credentials from IAM role
                self.duckdb_conn.execute(f"SET s3_access_key_id='{credentials.access_key}'")
                self.duckdb_conn.execute(f"SET s3_secret_access_key='{credentials.secret_key}'")
                if credentials.token:
                    self.duckdb_conn.execute(f"SET s3_session_token='{credentials.token}'")
            else:
                # Force DuckDB to use AWS SDK credential chain
                self.duckdb_conn.execute("SET s3_access_key_id=''")
                self.duckdb_conn.execute("SET s3_secret_access_key=''")
            
            # Set region and SSL settings
            aws_region = os.environ.get('AWS_REGION', 'ca-west-1')
            self.duckdb_conn.execute(f"SET s3_region='{aws_region}'")
            self.duckdb_conn.execute("SET s3_use_ssl=true")
            self.duckdb_conn.execute("SET s3_url_style='path'")
            self.duckdb_conn.execute(f"SET s3_endpoint='s3.{aws_region}.amazonaws.com'")
            
            logger.info("✅ DuckDB S3 configured successfully")
            
        except Exception as e:
            logger.error(f"Error configuring DuckDB for S3: {str(e)}")
            raise
    
    def create_s3_view(self, s3_bucket: str, s3_prefix: str = "public/raw_ohlcv"):
        """Create a DuckDB view that reads from S3 parquet files"""
        try:
            s3_path = f"s3://{s3_bucket}/{s3_prefix}/*.parquet"
            logger.info(f"Creating DuckDB view for S3 path: {s3_path}")
            
            # Create view
            create_view_sql = f"""
            CREATE OR REPLACE VIEW s3_ohlcv AS 
            SELECT * FROM read_parquet('{s3_path}')
            """
            
            self.duckdb_conn.execute(create_view_sql)
            logger.info(f"DuckDB view 's3_ohlcv' created successfully")
            
        except Exception as e:
            logger.error(f"Error creating S3 view: {str(e)}")
            raise
    
    def get_fibonacci_resampling_sql(self, interval: int, latest_timestamp: Optional[str] = None) -> str:
        """
        Generate DuckDB SQL for Fibonacci resampling using ROW_NUMBER approach
        
        CORRECT INCREMENTAL APPROACH:
        1. Resample ALL data from S3 (form complete intervals)
        2. Apply incremental filter AFTER resampling (on aggregated results)
        3. This ensures complete intervals are never partially formed
        """
        # Incremental filter applied AFTER resampling
        incremental_filter = ""
        if latest_timestamp:
            incremental_filter = f"AND start_date > '{latest_timestamp}'"
        
        sql = f"""
        WITH date_boundaries AS (
            SELECT 
                ts::DATE as date_val,
                symbol,
                MIN(ts) as first_ts,
                MAX(ts) as last_ts
            FROM s3_ohlcv
            GROUP BY ts::DATE, symbol
        ),
        day_numbers AS (
            SELECT 
                date_val,
                symbol,
                first_ts,
                last_ts,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date_val) as day_num
            FROM date_boundaries
        ),
        fibonacci_groups AS (
            SELECT 
                date_val,
                symbol,
                first_ts,
                last_ts,
                day_num,
                FLOOR((day_num - 1) / {interval}) as group_num
            FROM day_numbers
        ),
        aggregated AS (
            SELECT 
                MIN(fg.first_ts) as start_date,
                fg.symbol,
                FIRST(o.open ORDER BY o.ts) as open,
                MAX(o.high) as high,
                MIN(o.low) as low,
                FIRST(o.close ORDER BY o.ts DESC) as close,
                SUM(o.volume) as volume
            FROM fibonacci_groups fg
            JOIN s3_ohlcv o ON fg.symbol = o.symbol 
                AND o.ts >= fg.first_ts 
                AND o.ts <= fg.last_ts
            GROUP BY fg.symbol, fg.group_num
        )
        SELECT 
            start_date AS ts,
            symbol,
            open,
            high,
            low,
            close,
            volume
        FROM aggregated
        WHERE 1=1 {incremental_filter}
        ORDER BY ts, symbol
        """
        
        return sql
    
    def _get_latest_timestamp_from_s3(self, s3_prefix: str) -> Optional[str]:
        """Get the latest timestamp from existing S3 silver data for incremental processing"""
        try:
            s3_path = f"s3://{self.s3_bucket}/{s3_prefix}/*.parquet"
            
            # Check if any parquet files exist
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=s3_prefix,
                MaxKeys=1
            )
            
            if 'Contents' not in response:
                logger.info(f"No existing data found in s3://{self.s3_bucket}/{s3_prefix}/")
                return None
            
            # Query the max timestamp from existing parquet files
            query = f"""
            SELECT MAX(ts) as latest_timestamp 
            FROM read_parquet('{s3_path}')
            """
            
            result = self.duckdb_conn.execute(query).fetchone()
            if result and result[0]:
                latest_timestamp = result[0]
                # Convert to string format for SQL comparison
                if isinstance(latest_timestamp, str):
                    return latest_timestamp
                else:
                    return latest_timestamp.strftime('%Y-%m-%d')
            else:
                return None
                
        except Exception as e:
            logger.warning(f"Could not get latest timestamp from S3: {str(e)}")
            logger.info("Proceeding with full resampling")
            return None
    
    def _write_to_s3_parquet(self, df: pd.DataFrame, s3_prefix: str, interval: int):
        """Write DataFrame to S3 as partitioned Parquet files"""
        try:
            # Add a year/month partition column for efficient queries
            df['year'] = pd.to_datetime(df['ts']).dt.year
            df['month'] = pd.to_datetime(df['ts']).dt.month
            
            # Group by year/month for partitioning
            for (year, month), group_df in df.groupby(['year', 'month']):
                # Remove partition columns before writing
                output_df = group_df.drop(columns=['year', 'month'])
                
                # Create partitioned path
                partition_path = f"{s3_prefix}/year={year}/month={month:02d}"
                filename = f"data_{interval}d_{year}{month:02d}.parquet"
                s3_key = f"{partition_path}/{filename}"
                
                # Write to local temp file first (DuckDB can write directly to S3 but this is more reliable)
                temp_file = f"/tmp/{filename}"
                output_df.to_parquet(temp_file, engine='pyarrow', compression='snappy', index=False)
                
                # Upload to S3
                self.s3_client.upload_file(temp_file, self.s3_bucket, s3_key)
                logger.info(f"📦 Wrote {len(output_df)} records to s3://{self.s3_bucket}/{s3_key}")
                
                # Clean up temp file
                os.remove(temp_file)
            
            logger.info(f"✅ Successfully wrote {len(df)} total records to S3")
            
        except Exception as e:
            logger.error(f"Error writing to S3: {str(e)}")
            raise
    
    def process_interval(self, interval: int, s3_input_bucket: str) -> Dict:
        """Process a single resampling interval using DuckDB + S3 (write to S3)"""
        start_time = time.time()
        output_prefix = f"{self.s3_output_prefix}/silver_{interval}d"
        
        logger.info(f"Processing interval {interval}d → s3://{self.s3_bucket}/{output_prefix}/")
        
        # Create S3 view in DuckDB for reading bronze data
        self.create_s3_view(s3_input_bucket)
        
        # Check if we have existing silver data in S3 for incremental processing
        latest_timestamp = self._get_latest_timestamp_from_s3(output_prefix)
        
        if latest_timestamp:
            logger.info(f"Found existing data in s3://{self.s3_bucket}/{output_prefix}/, latest timestamp: {latest_timestamp}")
            logger.info(f"Resampling ALL data, then filtering for data after {latest_timestamp}")
        else:
            logger.info(f"No existing data in S3, performing full resampling")
        
        # Generate DuckDB resampling SQL with incremental filter
        resampling_sql = self.get_fibonacci_resampling_sql(interval, latest_timestamp)
        
        try:
            # Execute resampling in DuckDB
            logger.info(f"Executing DuckDB resampling for {interval}d...")
            result = self.duckdb_conn.execute(resampling_sql)
            
            # Fetch all results into a DataFrame for easy Parquet writing
            df = result.df()
            records_count = len(df)
            logger.info(f"DuckDB processed {records_count} records for {interval}d")
            
            if records_count == 0:
                logger.warning(f"No new data found for {interval}d interval")
                return {
                    'interval': interval,
                    'records_processed': 0,
                    'execution_time': time.time() - start_time,
                    'status': 'success'
                }
            
            # Write resampled data to S3 as partitioned Parquet
            logger.info(f"Writing {records_count} records to S3 as Parquet...")
            self._write_to_s3_parquet(df, output_prefix, interval)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            logger.info(f"✅ Completed {interval}d: {records_count} records in {execution_time:.2f}s")
            logger.info(f"📦 Output: s3://{self.s3_bucket}/{output_prefix}/")
            
            return {
                'interval': interval,
                'records_processed': records_count,
                'execution_time': execution_time,
                'status': 'success',
                's3_output': f"s3://{self.s3_bucket}/{output_prefix}/"
            } 
            
        except Exception as e:
            logger.error(f"Error processing {interval}d: {str(e)}")
            raise
    
    def close(self):
        """Clean up resources"""
        if self.duckdb_conn:
            self.duckdb_conn.close()
            logger.info("DuckDB connection closed")


def run_resampling_job(s3_bucket: str, intervals: List[int] = None):
    """Run resampling job for specified intervals"""
    if intervals is None:
        intervals = DuckDBS3Resampler.RESAMPLING_INTERVALS
    
    logger.info("============================================================")
    logger.info("STARTING RESAMPLING PROCESS")
    logger.info("============================================================")
    logger.info(f"🚀 Starting DuckDB + S3 Data Lake Resampling job")
    logger.info(f"📅 Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"📊 Will process {len(intervals)} intervals: {intervals}")
    
    try:
        resampler = DuckDBS3Resampler(s3_bucket=s3_bucket)
        
        results = []
        logger.info("🔄 Starting interval processing...")
        
        for idx, interval in enumerate(intervals, 1):
            logger.info(f"📈 Processing interval {idx}/{len(intervals)}: {interval}d")
            result = resampler.process_interval(interval, s3_bucket)
            results.append(result)
            
            # Log progress
            completed = idx
            remaining = len(intervals) - idx
            logger.info(f"Progress: {completed}/{len(intervals)} completed, {remaining} remaining")
        
        # Close connections
        resampler.close()
        
        # Summary
        total_records = sum(r['records_processed'] for r in results)
        total_time = sum(r['execution_time'] for r in results)
        
        logger.info("============================================================")
        logger.info("RESAMPLING JOB COMPLETED SUCCESSFULLY")
        logger.info("============================================================")
        logger.info(f"✅ Processed {len(intervals)} intervals")
        logger.info(f"📊 Total records: {total_records:,}")
        logger.info(f"⏱️  Total time: {total_time:.2f}s")
        logger.info(f"📦 Output location: s3://{s3_bucket}/silver/")
        
        return results
        
    except Exception as e:
        logger.error(f"Fatal error in AWS Batch Resampling job: {str(e)}")
        raise


def main():
    """Main entry point for AWS Batch job"""
    logger.info("Starting automated AWS Batch Resampling job (DuckDB + S3 Data Lake)")
    logger.info("============================================================")
    logger.info("AWS BATCH RESAMPLER STARTUP")
    logger.info("============================================================")
    
    # Get configuration from environment variables
    aws_region = os.environ.get('AWS_REGION', 'ca-west-1')
    s3_bucket = os.environ.get('S3_BUCKET_NAME', 'dev-condvest-datalake')
    intervals_env = os.environ.get('RESAMPLING_INTERVALS', '3,5,8,13,21,34')
    
    # Parse intervals
    try:
        intervals = [int(x.strip()) for x in intervals_env.split(',')]
    except ValueError as e:
        logger.error(f"Invalid RESAMPLING_INTERVALS format: {intervals_env}")
        raise
    
    logger.info(f"AWS_REGION: {aws_region}")
    logger.info(f"S3_BUCKET_NAME: {s3_bucket}")
    logger.info(f"RESAMPLING_INTERVALS: {intervals_env}")
    logger.info(f"Initializing DuckDBS3Resampler...")
    
    try:
        logger.info("✅ DuckDBS3Resampler initialized successfully")
        logger.info(f"📊 Processing Resampling intervals: {intervals}")
        logger.info(f"🪣 Using S3 bucket: {s3_bucket}")
        
        # Run the resampling job
        results = run_resampling_job(
            s3_bucket=s3_bucket,
            intervals=intervals
        )
        
        logger.info("🎉 AWS Batch Resampling job completed successfully!")
        return results
        
    except Exception as e:
        logger.error(f"❌ AWS Batch Resampling job failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()

