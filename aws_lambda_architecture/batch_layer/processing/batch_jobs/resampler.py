"""
Optimized OHLCV Resampler using DuckDB + S3 + RDS PostgreSQL
Purpose: High-performance resampling using DuckDB for S3 data processing

Cost-efficient approach that leverages:
- DuckDB for fast S3 data reading and resampling
- S3 for scalable data storage
- RDS PostgreSQL for final storage and serving
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

# Add shared utilities
sys.path.append('/opt/python')
from shared.clients.rds_timescale_client import RDSPostgresClient
from shared.utils.market_calendar import get_previous_trading_day

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DuckDBS3Resampler:
    """
    High-performance OHLCV resampling using DuckDB + S3 + RDS PostgreSQL
    
    Leverages:
    - DuckDB for fast S3 data reading and resampling
    - S3 for scalable data storage
    - RDS PostgreSQL for final storage and serving
    - Proven ROW_NUMBER approach optimized for DuckDB
    """
    
    # Fibonacci intervals 3-34 (matching your settings.yaml)
    RESAMPLING_INTERVALS = [3, 5, 8, 13, 21, 34]
    
    def __init__(self):
        """Initialize DuckDB and RDS connections"""
        # Initialize DuckDB connection
        self.duckdb_conn = duckdb.connect()
        
        # Configure DuckDB for S3 access
        self._setup_duckdb_s3_config()
        
        # Initialize RDS PostgreSQL client for final storage
        secret_arn = os.environ.get('RDS_SECRET_ARN')
        
        if secret_arn:
            self.rds_client = RDSPostgresClient(secret_arn=secret_arn)
        else:
            # Fallback to environment variables
            self.rds_client = RDSPostgresClient(
                endpoint=os.environ['RDS_ENDPOINT'],
                username=os.environ['RDS_USERNAME'],
                password=os.environ['RDS_PASSWORD'],
                database=os.environ['RDS_DATABASE']
            )
        
        logger.info("DuckDB + S3 + RDS Resampler initialized")
    
    def _setup_duckdb_s3_config(self):
        """Configure DuckDB for S3 access using AWS credentials"""
        try:
            # Set S3 region
            s3_region = os.environ.get('AWS_REGION', 'ca-west-1')
            self.duckdb_conn.execute(f"SET s3_region='{s3_region}'")
            
            # Set AWS credentials
            aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
            aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
            
            if aws_access_key and aws_secret_key:
                self.duckdb_conn.execute(f"SET s3_access_key_id='{aws_access_key}'")
                self.duckdb_conn.execute(f"SET s3_secret_access_key='{aws_secret_key}'")
            else:
                logger.warning("AWS credentials not found, DuckDB will use IAM roles")
            
            logger.info(f"DuckDB S3 configuration completed for region: {s3_region}")
            
        except Exception as e:
            logger.error(f"Error configuring DuckDB S3 access: {str(e)}")
            raise
        
    def create_s3_view(self, s3_bucket: str, s3_prefix: str = "public/raw_ohlcv"):
        """Create DuckDB view for S3 parquet data"""
        try:
            s3_path = f"s3://{s3_bucket}/{s3_prefix}/*.parquet"
            
            create_view_sql = f"""
            CREATE OR REPLACE VIEW s3_ohlcv AS
            SELECT * FROM read_parquet('{s3_path}');
            """
            
            self.duckdb_conn.execute(create_view_sql)
            logger.info(f"DuckDB view 's3_ohlcv' created for S3 path: {s3_path}")
            
        except Exception as e:
            logger.error(f"Error creating S3 view: {str(e)}")
            raise
    
    def get_symbols_to_process(self) -> List[str]:
        """Get all active symbols from RDS symbol metadata"""
        try:
            symbols = self.rds_client.get_active_symbols()
            logger.info(f"Found {len(symbols)} active symbols to process")
            return symbols
        except Exception as e:
            logger.error(f"Error fetching symbols: {str(e)}")
            raise
    
    def create_silver_table_if_not_exists(self, interval: int):
        """Create PostgreSQL-optimized silver table for specific interval"""
        table_name = f"silver_{interval}d"
        
        create_table_sql = f"""
        -- Create the table if it doesn't exist
            CREATE TABLE IF NOT EXISTS {table_name} (
            timestamp TIMESTAMPTZ NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            open DECIMAL(12,4) NOT NULL,
            high DECIMAL(12,4) NOT NULL,
            low DECIMAL(12,4) NOT NULL,
            close DECIMAL(12,4) NOT NULL,
            volume BIGINT NOT NULL,
            interval INTEGER DEFAULT {interval},    
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (timestamp, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_timestamp ON {table_name}(symbol, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name}(timestamp DESC);

        """
        
        try:
            self.rds_client.execute_query(create_table_sql)
            logger.info(f"PostgreSQL table {table_name} created/verified")
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {str(e)}")
            raise
    
    def get_fibonacci_resampling_sql(self, interval: int, latest_timestamp: Optional[str] = None) -> str:
        """
        Generate DuckDB resampling SQL for Fibonacci intervals with incremental support
        
        CORRECT APPROACH: Resample ALL data first, then filter by latest timestamp
        This ensures:
        - Complete intervals are formed properly
        - ROW_NUMBER() works on complete datasets
        - No partial intervals are lost
        
        Args:
            interval: Fibonacci interval (3, 5, 8, 13, 21, 34)
            latest_timestamp: Optional latest timestamp for incremental processing
        """
        
        # Add incremental filter AFTER resampling if latest_timestamp is provided
        incremental_filter = ""
        if latest_timestamp:
            incremental_filter = f"AND start_date > '{latest_timestamp}'"
                
        sql = f"""
            WITH numbered AS (
                SELECT
                    symbol,
                    CAST(timestamp_1 AS DATE) AS date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY CAST(timestamp_1 AS DATE)) AS rn
                FROM s3_ohlcv
                WHERE interval = '1d'
                ORDER BY symbol, date
            ),
            grp AS (
                SELECT
                    symbol,
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    CAST(FLOOR((rn - 1) / {interval}) AS INTEGER) AS grp_id
                FROM numbered
            ),
            aggregated AS (
                SELECT
                    symbol,
                    grp_id,
                    MIN(date) AS start_date,
                    MAX(high) AS high,
                    MIN(low) AS low,
                    SUM(volume) AS volume,
                    FIRST(open ORDER BY date) AS open,
                    FIRST(close ORDER BY date DESC) AS close
                FROM grp
                GROUP BY symbol, grp_id
                HAVING COUNT(*) = {interval}
            )
            SELECT
                symbol,
                start_date AS timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM aggregated
            WHERE 1=1 {incremental_filter}
            ORDER BY symbol, start_date
        """
        
        return sql
    
    def process_interval(self, interval: int, s3_bucket: str) -> Dict[str, any]:
        """
        Process a single Fibonacci interval using DuckDB + S3 + RDS with incremental updates
        
        CORRECT APPROACH: 
        1. Resample ALL data from S3 (complete intervals)
        2. Filter results by latest timestamp from RDS (only new data)
        3. Insert only new resampled data to RDS
        
        This ensures complete intervals are formed and no partial data is lost.
        
        Args:
            interval: Fibonacci interval (3, 5, 8, 13, 21, 34)
            s3_bucket: S3 bucket containing parquet data
        """
        start_time = time.time()
        table_name = f"silver_{interval}d"
        
        logger.info(f"Processing interval {interval}d (table: {table_name}) using DuckDB + S3 with incremental updates")
        
        # Create RDS table if needed
        self.create_silver_table_if_not_exists(interval)
        
        # Create S3 view in DuckDB
        self.create_s3_view(s3_bucket)
        
        # Get latest timestamp from RDS table for incremental processing
        latest_timestamp = self._get_latest_timestamp_from_rds(table_name)
        
        if latest_timestamp:
            logger.info(f"Found existing data in {table_name}, latest timestamp: {latest_timestamp}")
            logger.info(f"Resampling ALL data, then filtering for data after {latest_timestamp}")
        else:
            logger.info(f"No existing data in {table_name}, performing full resampling")
        
        # Generate DuckDB resampling SQL with incremental filter
        resampling_sql = self.get_fibonacci_resampling_sql(interval, latest_timestamp)
        
        try:
            # Execute resampling in DuckDB and get results as DuckDB result set (no DataFrame conversion)
            logger.info(f"Executing DuckDB resampling for {interval}d...")
            result = self.duckdb_conn.execute(resampling_sql)
            
            # Get count without converting to DataFrame
            count_result = self.duckdb_conn.execute(f"SELECT COUNT(*) FROM ({resampling_sql}) AS resampled_data").fetchone()
            records_count = count_result[0] if count_result else 0
            
            logger.info(f"DuckDB processed {records_count} records for {interval}d")
            
            if records_count == 0:
                logger.warning(f"No new data found for {interval}d interval")
                return {
                    'interval': interval,
                    'records_processed': 0,
                    'execution_time': time.time() - start_time,
                    'status': 'success'
                }
            
            # Insert resampled data directly from DuckDB result set to RDS PostgreSQL
            logger.info(f"Inserting {records_count} records into RDS table {table_name}")
            self._insert_duckdb_result_to_rds(result, table_name)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            logger.info(f"Completed {interval}d: {records_count} records in {execution_time:.2f}s")
            
            return {
                'interval': interval,
                'records_processed': records_count,
                'execution_time': execution_time,
                'status': 'success'
            } 
            
        except Exception as e:
            logger.error(f"Error processing {interval}d: {str(e)}")
            raise
    
    def _get_latest_timestamp_from_rds(self, table_name: str) -> Optional[str]:
        """Get the latest timestamp from RDS table for incremental processing"""
        try:
            query = f"""
            SELECT MAX(timestamp) as latest_timestamp 
            FROM {table_name}
            """
            
            result = self.rds_client.execute_query(query)
            if result and result[0]['latest_timestamp']:
                latest_timestamp = result[0]['latest_timestamp']
                # Convert to string format for SQL comparison
                if isinstance(latest_timestamp, str):
                    return latest_timestamp
                else:
                    return latest_timestamp.strftime('%Y-%m-%d')
            else:
                logger.info(f"No existing data found in {table_name}")
                return None
                
        except Exception as e:
            logger.warning(f"Error getting latest timestamp from {table_name}: {str(e)}")
            logger.info("Proceeding with full resampling")
            return None
    
    def _insert_duckdb_result_to_rds(self, duckdb_result, table_name: str):
        """Insert DuckDB result set directly into RDS PostgreSQL table using optimized batch insert"""
        try:
            # Fetch all results at once (DuckDB handles memory efficiently)
            all_data = duckdb_result.fetchall()
            
            if not all_data:
                logger.info(f"No data to insert into {table_name}")
                return
            
            # Convert to list of tuples for batch insert
            data_tuples = [tuple(row) for row in all_data]
            
            # Use optimized batch insert method
            total_inserted = self.rds_client.insert_silver_batch(table_name, data_tuples)
            
            logger.info(f"Successfully inserted {total_inserted} records into {table_name}")
            
        except Exception as e:
            logger.error(f"Error inserting DuckDB result to RDS table {table_name}: {str(e)}")
            raise

    def _insert_dataframe_to_rds(self, df: pd.DataFrame, table_name: str):
        """Insert DataFrame data into RDS PostgreSQL table using optimized batch insert (fallback method)"""
        try:
            # Convert DataFrame to list of tuples for batch insert
            data_tuples = [tuple(row) for row in df.values]
            
            # Use optimized batch insert method
            total_inserted = self._execute_batch_insert(table_name, data_tuples)
            
            logger.info(f"Successfully inserted {total_inserted} records into {table_name}")
            
        except Exception as e:
            logger.error(f"Error inserting DataFrame to RDS table {table_name}: {str(e)}")
            raise
    
    def run_resampling_job(self, s3_bucket: str, intervals: List[int] = None) -> Dict[str, any]:
        """
        Run the complete Resampling job using DuckDB + S3 + RDS
        
        Args:
            s3_bucket: S3 bucket containing parquet data
            intervals: Optional list of intervals to process (default: 3-34 Resampling)
        """
        start_time = time.time()
        logger.info("Starting DuckDB + S3 + RDS Resampling job (3-34)")
        
        # Use Resampling intervals 3-34 if not specified
        if intervals is None:
            intervals = self.RESAMPLING_INTERVALS
        
        # Process each interval
        total_stats = {
            'intervals_processed': 0,
            'total_records': 0,
            'errors': 0,
            'start_time': start_time,
            'intervals': intervals,
            'details': []
        }
        
        for interval in intervals:
            try:
                interval_stats = self.process_interval(interval, s3_bucket)
                
                total_stats['intervals_processed'] += 1
                total_stats['total_records'] += interval_stats['records_processed']
                total_stats['details'].append(interval_stats)
                
                logger.info(f"✅ Interval {interval}d: {interval_stats['records_processed']} records")
                
            except Exception as e:
                logger.error(f"❌ Error processing interval {interval}d: {str(e)}")
                total_stats['errors'] += 1
                total_stats['details'].append({
                    'interval': interval,
                    'status': 'error',
                    'error': str(e)
                })
        
        end_time = time.time()
        total_stats['end_time'] = end_time
        total_stats['duration_seconds'] = end_time - start_time
        
        logger.info(f"Resampling job completed: {total_stats}")
        return total_stats
    
    def close(self):
        """Close DuckDB and RDS connections"""
        try:
            if hasattr(self, 'duckdb_conn'):
                self.duckdb_conn.close()
                logger.info("DuckDB connection closed")
            
            if hasattr(self, 'rds_client') and hasattr(self.rds_client, 'close'):
                self.rds_client.close()
                logger.info("RDS connection closed")
                
        except Exception as e:
            logger.error(f"Error closing connections: {str(e)}")

def main():
    """
    Main entry point for automated AWS Batch Resampling job using DuckDB + S3 + RDS
    
    Configuration comes from environment variables set in the AWS Batch Job Definition
    """
    
    try:
        logger.info("Starting automated AWS Batch Resampling job (DuckDB + S3 + RDS)")
        resampler = DuckDBS3Resampler()
        
        # Get S3 bucket from environment variable
        s3_bucket = os.environ.get('S3_BUCKET_NAME', 'dev-condvest-datalake')
        
        # Get intervals from environment variable (set by Terraform)
        intervals_env = os.environ.get('RESAMPLING_INTERVALS', '3,5,8,13,21,34')
        intervals = [int(x.strip()) for x in intervals_env.split(',')]
        
        logger.info(f"Processing Resampling intervals: {intervals}")
        logger.info(f"Using S3 bucket: {s3_bucket}")
        
        # Run Resampling job using DuckDB + S3 + RDS
        job_stats = resampler.run_resampling_job(s3_bucket=s3_bucket, intervals=intervals)
        
        # Log final statistics
        logger.info("="*60)
        logger.info("AWS BATCH RESAMPLING JOB SUMMARY (DuckDB + S3 + RDS)")
        logger.info("="*60)
        logger.info(f"Intervals Processed: {job_stats['intervals_processed']}")
        logger.info(f"Total Records: {job_stats['total_records']}")
        logger.info(f"Errors: {job_stats['errors']}")
        logger.info(f"Duration: {job_stats['duration_seconds']:.2f} seconds")
        logger.info("="*60)
        
        # Return success (AWS Batch will see this exit code)
        return 0 if job_stats['errors'] == 0 else 1
        
    except Exception as e:
        logger.error(f"Fatal error in AWS Batch Resampling job: {str(e)}")
        return 1
    finally:
        if 'resampler' in locals():
            resampler.close()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
