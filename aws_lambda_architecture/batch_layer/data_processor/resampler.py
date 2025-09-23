"""
Optimized OHLCV Resampler for Aurora PostgreSQL
Purpose: High-performance resampling using Aurora's analytical capabilities

Inspired by your DuckDB implementation but optimized for Aurora PostgreSQL.
Uses your proven ROW_NUMBER windowing approach for Fibonacci intervals 3-34.
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
# Removed argparse - not needed for automated AWS Batch execution

# Add shared utilities
sys.path.append('/opt/python')
from shared.clients.aurora_client import AuroraClient
from shared.utils.market_calendar import get_previous_trading_day

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AuroraFibonacciResampler:
    """
    High-performance OHLCV resampling using Aurora PostgreSQL
    
    Mimics your DuckDB implementation but leverages Aurora's:
    - Columnar storage (Aurora I/O optimized)
    - Parallel query execution  
    - Window functions
    - Your proven ROW_NUMBER approach
    """
    
    # Fibonacci intervals 3-34 (matching your settings.yaml)
    FIBONACCI_INTERVALS = [3, 5, 8, 13, 21, 34]
    
    def __init__(self):
        self.aurora_client = AuroraClient(
            cluster_arn=os.environ['AURORA_CLUSTER_ARN'],
            secret_arn=os.environ['AURORA_SECRET_ARN'],
            database_name=os.environ['DATABASE_NAME']
        )
        logger.info("Aurora Fibonacci Resampler initialized")
        
    def get_symbols_to_process(self) -> List[str]:
        """Get all active symbols from symbol metadata"""
        try:
            symbols = self.aurora_client.get_active_symbols()
            logger.info(f"Found {len(symbols)} active symbols to process")
            return symbols
        except Exception as e:
            logger.error(f"Error fetching symbols: {str(e)}")
            raise
    
    def create_silver_table_if_not_exists(self, interval: int):
        """Create silver table for specific interval if it doesn't exist"""
        table_name = f"silver_{interval}d"
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            open DECIMAL(10,2) NOT NULL,
            high DECIMAL(10,2) NOT NULL,
            low DECIMAL(10,2) NOT NULL,
            close DECIMAL(10,2) NOT NULL,
            volume BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        
        -- Performance indexes (matching your speed layer approach)
        CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name}(date DESC);
        CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC);
        """
        
        try:
            self.aurora_client.execute_query(create_table_sql)
            logger.info(f"Table {table_name} created/verified")
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {str(e)}")
            raise
    
    def get_last_processed_date(self, interval: int) -> Optional[date]:
        """Get the last processed date for a specific interval (for incremental processing)"""
        table_name = f"silver_{interval}d"
        
        try:
            query = f"SELECT MAX(date) FROM {table_name}"
            result = self.aurora_client.execute_query(query)
            
            if result and result[0][0]:
                return result[0][0]
            return None
            
        except Exception as e:
            logger.debug(f"Table {table_name} might not exist yet: {str(e)}")
            return None
    
    def get_fibonacci_resampling_sql(self, interval: int) -> str:
        """
        Generate high-performance resampling SQL using your proven DuckDB approach
        
        SIMPLIFIED: Always does full resampling (no incremental complexity)
        This SQL directly mimics your DuckDB logic:
        - Uses ROW_NUMBER() for grouping (exactly like your implementation)
        - Uses FIRST_VALUE/LAST_VALUE for open/close (Aurora equivalent of FIRST/LAST)
        - Leverages Aurora's columnar storage for performance
        """
        
        # PostgreSQL-compatible SQL with proper aggregation handling
        # SIMPLIFIED: No date filtering, always process all data
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
                    WHERE interval = '1d'
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
                        -- Get first open and last close using arrays (PostgreSQL approach)
                        (array_agg(open ORDER BY date))[1] AS open,
                        (array_agg(close ORDER BY date DESC))[1] AS close
                    FROM grp
                    GROUP BY symbol, grp_id
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
        Process a single Fibonacci interval with high performance
        
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
        count_query = f"SELECT COUNT(*) FROM ({resampling_sql}) AS resampled_data"
        try:
            count_result = self.aurora_client.execute_query(count_query)
            records_count = count_result[0][0] if count_result else 0
            
            logger.info(f"Will process {records_count} records for {interval}d")
            
        except Exception as e:
            logger.error(f"Error counting records for {interval}d: {str(e)}")
            raise
        
        # SIMPLIFIED: Clear existing data and insert fresh resampled data
        logger.info(f"Clearing existing data in {table_name}")
        clear_sql = f"DELETE FROM {table_name}"
        
        insert_sql = f"""
        INSERT INTO {table_name} (symbol, date, open, high, low, close, volume)
        {resampling_sql}
        """
        
        try:
            # Clear existing data
            self.aurora_client.execute_query(clear_sql)
            
            # Insert fresh resampled data
            self.aurora_client.execute_query(insert_sql)
            
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
    
    def run_fibonacci_resampling_job(self, intervals: List[int] = None) -> Dict[str, any]:
        """
        Run the complete Fibonacci resampling job for intervals 3-34
        
        SIMPLIFIED: Always does full resampling (no incremental complexity)
        
        Args:
            intervals: Optional list of intervals to process (default: 3-34 Fibonacci)
        """
        start_time = time.time()
        logger.info("Starting Aurora-based Fibonacci resampling job (3-34) - FULL RESAMPLING")
        
        # Use Fibonacci intervals 3-34 if not specified
        if intervals is None:
            intervals = self.FIBONACCI_INTERVALS
        
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
        
        logger.info(f"Fibonacci resampling job completed: {total_stats}")
        return total_stats
    
    def optimize_tables(self):
        """Run VACUUM and ANALYZE on silver tables for performance"""
        logger.info("Optimizing silver tables...")
        
        for interval in self.FIBONACCI_INTERVALS:
            table_name = f"silver_{interval}d"
            try:
                # ANALYZE for query planner statistics
                self.aurora_client.execute_query(f"ANALYZE {table_name}")
                logger.debug(f"Analyzed table {table_name}")
            except Exception as e:
                logger.warning(f"Could not analyze table {table_name}: {str(e)}")
        
        logger.info("Table optimization completed")
    
    def get_performance_stats(self) -> Dict[str, any]:
        """Get performance statistics for monitoring"""
        stats = {}
        
        for interval in self.FIBONACCI_INTERVALS:
            table_name = f"silver_{interval}d"
            try:
                # Get table size and row count
                size_query = f"""
                SELECT 
                    COUNT(*) as row_count,
                    pg_size_pretty(pg_total_relation_size('{table_name}')) as table_size
                FROM {table_name}
                """
                result = self.aurora_client.execute_query(size_query)
                
                if result:
                    stats[f"{interval}d"] = {
                        'row_count': result[0][0],
                        'table_size': result[0][1]
                    }
                    
            except Exception as e:
                logger.warning(f"Could not get stats for {table_name}: {str(e)}")
        
        return stats
    
    def close(self):
        """Close Aurora connection"""
        if hasattr(self.aurora_client, 'close'):
            self.aurora_client.close()
        logger.info("Aurora connection closed")

def main():
    """
    Main entry point for automated AWS Batch Fibonacci resampling job
    
    No command-line arguments needed - this runs automatically after daily_ohlcv_fetcher
    Configuration comes from environment variables set by AWS Batch
    """
    
    try:
        logger.info("Starting automated AWS Batch Fibonacci resampling job")
        resampler = AuroraFibonacciResampler()
        
        # Get intervals from environment variable (set by Terraform)
        intervals_env = os.environ.get('FIBONACCI_INTERVALS', '3,5,8,13,21,34')
        intervals = [int(x.strip()) for x in intervals_env.split(',')]
        
        logger.info(f"Processing Fibonacci intervals: {intervals}")
        
        # Run Fibonacci resampling job (ALWAYS FULL RESAMPLING)
        job_stats = resampler.run_fibonacci_resampling_job(intervals=intervals)
        
        # Optimize tables after processing
        resampler.optimize_tables()
        
        # Log final statistics
        logger.info("="*60)
        logger.info("AWS BATCH FIBONACCI RESAMPLING JOB SUMMARY")
        logger.info("="*60)
        logger.info(f"Intervals Processed: {job_stats['intervals_processed']}")
        logger.info(f"Total Records: {job_stats['total_records']}")
        logger.info(f"Errors: {job_stats['errors']}")
        logger.info(f"Duration: {job_stats['duration_seconds']:.2f} seconds")
        logger.info("="*60)
        
        # Return success (AWS Batch will see this exit code)
        return 0 if job_stats['errors'] == 0 else 1
        
    except Exception as e:
        logger.error(f"Fatal error in AWS Batch Fibonacci resampling job: {str(e)}")
        return 1
    finally:
        if 'resampler' in locals():
            resampler.close()

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
