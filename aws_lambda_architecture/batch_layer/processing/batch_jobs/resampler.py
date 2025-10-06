"""
Optimized OHLCV Resampler for RDS PostgreSQL + TimescaleDB
Purpose: High-performance resampling using TimescaleDB's time-series capabilities

Cost-efficient alternative to Aurora, optimized for Fibonacci intervals 3-34.
Uses your proven ROW_NUMBER windowing approach from DuckDB implementation.
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional

# Add shared utilities
sys.path.append('/opt/python')
from shared.clients.rds_timescale_client import RDSPostgresClient # Corrected import
from shared.utils.market_calendar import get_previous_trading_day

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RDSPostgresResampler: # Renamed class
    """
    High-performance OHLCV resampling using RDS PostgreSQL
    
    Mimics your DuckDB implementation but leverages PostgreSQL's:
    - Declarative partitioning for automatic data management
    - Your proven ROW_NUMBER approach
    """
    
    # Fibonacci intervals 3-34 (matching your settings.yaml)
    RESAMPLING_INTERVALS = [3, 5, 8, 13, 21, 34]
    
    def __init__(self):
        """Initialize with RDS PostgreSQL connection"""
        # Use AWS Secrets Manager for credentials
        secret_arn = os.environ.get('RDS_SECRET_ARN')
        
        if secret_arn:
            self.db_client = RDSPostgresClient(secret_arn=secret_arn)
        else:
            # Fallback to environment variables
            self.db_client = RDSPostgresClient(
                endpoint=os.environ['RDS_ENDPOINT'],
                username=os.environ['RDS_USERNAME'],
                password=os.environ['RDS_PASSWORD'],
                database=os.environ['RDS_DATABASE']
            )
        
        logger.info("RDS PostgreSQL Resampler initialized")
        
    def get_symbols_to_process(self) -> List[str]:
        """Get all active symbols from symbol metadata"""
        try:
            symbols = self.db_client.get_active_symbols()
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
        CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC);
        CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name}(date DESC);

        """
        
        try:
            self.db_client.execute_query(create_table_sql)
            logger.info(f"PostgreSQL table {table_name} created/verified")
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {str(e)}")
            raise
    
    def get_fibonacci_resampling_sql(self, interval: int) -> str:
        """
        Generate high-performance resampling SQL using your proven DuckDB approach
        
        SIMPLIFIED: Always does full resampling (no incremental complexity)
        This SQL directly mimics your DuckDB logic but optimized for PostgreSQL:
        - Uses ROW_NUMBER() for grouping (exactly like your implementation)
        - Uses array_agg() for open/close (PostgreSQL equivalent of FIRST/LAST)
        - Leverages PostgreSQL's time-series optimizations (via partitioning set up separately)
        """
        
        # PostgreSQL compatible SQL with proper aggregation handling
        sql = f"""
        WITH numbered AS (
            SELECT
                symbol,
                DATE(timestamp) as date,
                open as open,
                high as high,
                low as low,
                close as close,
                volume,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY DATE(timestamp)) AS rn
            FROM raw_ohlcv
            WHERE interval = '1d' -- Corrected: filtering on 'interval' column
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
                (rn - 1) / {interval} AS grp_id
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
                -- PostgreSQL approach: use array_agg with ordering
                (array_agg(open ORDER BY date))[1] AS open,
                (array_agg(close ORDER BY date DESC))[1] AS close
            FROM grp
            GROUP BY symbol, grp_id
            HAVING COUNT(*) = {interval}  -- Only complete intervals
        )
        SELECT
            symbol,
            start_date AS date,
            open,
            high,
            low,
            close,
            volume
        FROM aggregated
        ORDER BY symbol, date
        """
        
        return sql
    
    def process_interval(self, interval: int) -> Dict[str, any]:
        """
        Process a single Fibonacci interval with TimescaleDB optimization
        
        SIMPLIFIED: Always does full resampling (no incremental complexity)
        
        Args:
            interval: Fibonacci interval (3, 5, 8, 13, 21, 34)
        """
        start_time = time.time()
        table_name = f"silver_{interval}d"
        
        logger.info(f"Processing interval {interval}d (table: {table_name}) - FULL RESAMPLING")
        
        # Create table if needed
        self.create_silver_table_if_not_exists(interval)
        
        # Generate resampling SQL using your DuckDB approach
        resampling_sql = self.get_fibonacci_resampling_sql(interval)
        
        # Count how many records we'll process
        count_query = f"SELECT COUNT(*) as count FROM ({resampling_sql}) AS resampled_data"
        try:
            count_result = self.db_client.execute_query(count_query)
            records_count = count_result[0]['count'] if count_result else 0
            
            logger.info(f"Will process {records_count} records for {interval}d")
            
        except Exception as e:
            logger.error(f"Error counting records for {interval}d: {str(e)}")
            raise
        
        # SIMPLIFIED: Clear existing data and insert fresh resampled data
        logger.info(f"Clearing existing data in {table_name}")
        clear_sql = f"DELETE FROM {table_name}"
        
        insert_sql = f"""
        INSERT INTO {table_name} (timestamp, symbol, open, high, low, close, volume)
        {resampling_sql}
        """
        
        try:
            # Clear existing data
            self.db_client.execute_query(clear_sql)
            
            # Insert fresh resampled data
            self.db_client.execute_query(insert_sql)
            
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
    
    def run_resampling_job(self, intervals: List[int] = None) -> Dict[str, any]:
        """
        Run the complete Resampling job for intervals 3-34
        
        SIMPLIFIED: Always does full resampling (no incremental complexity)
        
        Args:
            intervals: Optional list of intervals to process (default: 3-34 Resampling)
        """
        start_time = time.time()
        logger.info("Starting RDS PostgreSQL Resampling job (3-34) - FULL RESAMPLING")
        
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
                interval_stats = self.process_interval(interval)
                
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
        """Close RDS PostgreSQL connection"""
        if hasattr(self.db_client, 'close'):
            self.db_client.close()
        logger.info("RDS PostgreSQL connection closed")

def main():
    """
    Main entry point for automated AWS Batch Resampling job
    
    No command-line arguments needed - this runs automatically after daily_ohlcv_fetcher
    Configuration comes from environment variables set in the AWS Batch Job Definition
    """
    
    try:
        logger.info("Starting automated AWS Batch Resampling job (RDS PostgreSQL)")
        resampler = RDSPostgresResampler()
        
        # Get intervals from environment variable (set by Terraform)
        intervals_env = os.environ.get('RESAMPLING_INTERVALS', '3,5,8,13,21,34')
        intervals = [int(x.strip()) for x in intervals_env.split(',')]
        
        logger.info(f"Processing Resampling intervals: {intervals}")
        
        # Run Resampling job (ALWAYS FULL RESAMPLING)
        job_stats = resampler.run_resampling_job(intervals=intervals)
        
        # Log final statistics
        logger.info("="*60)
        logger.info("AWS BATCH RESAMPLING JOB SUMMARY (RDS PostgreSQL)")
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
