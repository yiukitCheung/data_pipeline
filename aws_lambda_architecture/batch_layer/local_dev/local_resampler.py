#!/usr/bin/env python3
"""
Local Fibonacci Resampler for Testing
Purpose: Test Fibonacci resampling logic locally before AWS deployment

This uses the EXACT same SQL logic as the AWS Aurora version,
but runs against local TimescaleDB for development testing.
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
import psycopg2
import argparse

# Add shared utilities (from parent directories)
sys.path.append('/app')
sys.path.append('/app/shared')
sys.path.append('../shared')
sys.path.append('../../shared')

try:
    from shared.clients.local_postgres_client import LocalPostgresClient
except ImportError:
    # Fallback for direct connection
    LocalPostgresClient = None
    print("Warning: Could not import LocalPostgresClient, using direct psycopg2")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LocalFibonacciResampler:
    """
    Local Fibonacci Resampler for testing
    
    Uses the EXACT same logic as AuroraFibonacciResampler,
    but connects to local TimescaleDB for development testing.
    """
    
    # Fibonacci intervals 3-34 (matching AWS version)
    FIBONACCI_INTERVALS = [3, 5, 8, 13, 21, 34]
    
    def __init__(self, database_url: str = None):
        """
        Initialize local resampler
        
        Args:
            database_url: PostgreSQL connection string
        """
        # Get database URL from environment or parameter
        self.database_url = database_url or os.environ.get(
            'DATABASE_URL', 
            'postgresql://yiukitcheung:409219@localhost:5434/condvest'
        )
        
        # Try to use shared client first, fallback to direct connection
        if LocalPostgresClient:
            try:
                self.db_client = LocalPostgresClient(self.database_url)
                logger.info("Using LocalPostgresClient for database connection")
            except Exception as e:
                logger.warning(f"Could not use LocalPostgresClient: {e}")
                self.db_client = None
        else:
            self.db_client = None
        
        # Test connection
        self._test_connection()
        logger.info("Local Fibonacci Resampler initialized")
        
    def _test_connection(self):
        """Test database connection"""
        try:
            if self.db_client:
                # Test using shared client
                result = self.db_client.execute_query("SELECT 1")
                logger.info("Database connection successful (via shared client)")
            else:
                # Test using direct connection
                conn = psycopg2.connect(self.database_url)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                conn.close()
                logger.info("Database connection successful (direct psycopg2)")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            raise
    
    def execute_query(self, query: str, params: tuple = None) -> List[tuple]:
        """Execute SQL query with error handling"""
        try:
            if self.db_client:
                # Use shared client
                return self.db_client.execute_query(query, params)
            else:
                # Use direct connection
                conn = psycopg2.connect(self.database_url)
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if cursor.description:  # SELECT query
                    result = cursor.fetchall()
                else:  # INSERT/UPDATE/DELETE
                    result = []
                
                conn.commit()
                cursor.close()
                conn.close()
                return result
                
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
    
    def get_symbols_to_process(self) -> List[str]:
        """Get all active symbols from symbol metadata"""
        try:
            query = """
            SELECT symbol 
            FROM test_symbol_metadata 
            WHERE is_active = true 
              AND symbol != '_SAMPLE_DATA_LOADED_'
            ORDER BY symbol
            """
            
            result = self.execute_query(query)
            symbols = [row[0] for row in result]
            
            logger.info(f"Found {len(symbols)} active symbols to process: {symbols}")
            return symbols
            
        except Exception as e:
            logger.error(f"Error fetching symbols: {str(e)}")
            raise
    
    def create_silver_table_if_not_exists(self, interval: int):
        """Create silver table for specific interval if it doesn't exist"""
        table_name = f"test_silver_{interval}d"
        
        # Check if table exists
        check_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = %s
        )
        """
        
        exists = self.execute_query(check_query, (table_name,))[0][0]
        
        if not exists:
            create_table_sql = f"""
            CREATE TABLE {table_name} (
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
            
            -- Performance indexes
            CREATE INDEX idx_{table_name}_date ON {table_name}(date DESC);
            CREATE INDEX idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC);
            """
            
            self.execute_query(create_table_sql)
            logger.info(f"Created table {table_name}")
        else:
            logger.info(f"Table {table_name} already exists")
    
    def get_fibonacci_resampling_sql(self, interval: int) -> str:
        """
        Generate Fibonacci resampling SQL using your proven DuckDB approach
        
        This is the EXACT same SQL as the AWS Aurora version!
        """
        
        # Fixed PostgreSQL-compatible SQL with proper window function handling
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
            FROM test_raw_ohlcv
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
        Process a single Fibonacci interval
        
        EXACTLY the same logic as AWS version!
        """
        start_time = time.time()
        table_name = f"test_silver_{interval}d"
        
        logger.info(f"Processing interval {interval}d (table: {table_name}) - LOCAL TESTING")
        
        # Create table if needed
        self.create_silver_table_if_not_exists(interval)
        
        # Generate resampling SQL using your DuckDB approach
        resampling_sql = self.get_fibonacci_resampling_sql(interval)
        
        # Count how many records we'll process
        count_query = f"SELECT COUNT(*) FROM ({resampling_sql}) AS resampled_data"
        try:
            count_result = self.execute_query(count_query)
            records_count = count_result[0][0] if count_result else 0
            
            logger.info(f"Will process {records_count} records for {interval}d")
            
        except Exception as e:
            logger.error(f"Error counting records for {interval}d: {str(e)}")
            raise
        
        # Clear existing data and insert fresh resampled data
        logger.info(f"Clearing existing data in {table_name}")
        clear_sql = f"DELETE FROM {table_name}"
        
        insert_sql = f"""
        INSERT INTO {table_name} (symbol, date, open, high, low, close, volume)
        {resampling_sql}
        """
        
        try:
            # Clear existing data
            self.execute_query(clear_sql)
            
            # Insert fresh resampled data
            self.execute_query(insert_sql)
            
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
        Run the complete Fibonacci resampling job
        
        EXACTLY the same logic as AWS version!
        """
        start_time = time.time()
        logger.info("Starting LOCAL Fibonacci resampling job (3-34) - TESTING MODE")
        
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
        
        logger.info(f"LOCAL Fibonacci resampling job completed: {total_stats}")
        return total_stats
    
    def show_results(self, intervals: List[int] = None):
        """Show resampling results for inspection"""
        if intervals is None:
            intervals = self.FIBONACCI_INTERVALS
        
        logger.info("\n" + "="*60)
        logger.info("LOCAL FIBONACCI RESAMPLING RESULTS")
        logger.info("="*60)
        
        for interval in intervals:
            table_name = f"test_silver_{interval}d"
            
            try:
                # Get record count and sample data
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                count_result = self.execute_query(count_query)
                count = count_result[0][0] if count_result else 0
                
                sample_query = f"""
                SELECT symbol, date, open, high, low, close, volume 
                FROM {table_name} 
                ORDER BY symbol, date 
                LIMIT 3
                """
                sample_result = self.execute_query(sample_query)
                
                logger.info(f"\n{interval}d Interval: {count} total records")
                
                if sample_result:
                    logger.info("Sample records:")
                    for row in sample_result:
                        logger.info(f"  {row[0]} | {row[1]} | O:{row[2]} H:{row[3]} L:{row[4]} C:{row[5]} V:{row[6]}")
                else:
                    logger.info("  No records found")
                    
            except Exception as e:
                logger.error(f"Error querying {table_name}: {str(e)}")
        
        logger.info("="*60)
    
    def validate_data_integrity(self):
        """Validate that resampling worked correctly"""
        logger.info("\n🔍 VALIDATING DATA INTEGRITY...")
        
        # Check raw data count
        raw_query = "SELECT symbol, COUNT(*) FROM test_raw_ohlcv WHERE interval = '1d' GROUP BY symbol"
        raw_result = self.execute_query(raw_query)
        
        logger.info("Raw data counts:")
        raw_counts = {}
        for row in raw_result:
            symbol, count = row[0], row[1]
            raw_counts[symbol] = count
            logger.info(f"  {symbol}: {count} daily records")
        
        # Check resampled data makes sense
        for interval in self.FIBONACCI_INTERVALS:
            table_name = f"test_silver_{interval}d"
            
            resampled_query = f"SELECT symbol, COUNT(*) FROM {table_name} GROUP BY symbol"
            resampled_result = self.execute_query(resampled_query)
            
            logger.info(f"\n{interval}d resampled data:")
            for row in resampled_result:
                symbol, resampled_count = row[0], row[1]
                raw_count = raw_counts.get(symbol, 0)
                expected_max = raw_count // interval  # Maximum possible complete intervals
                
                if resampled_count <= expected_max:
                    status = "✅ Valid"
                else:
                    status = "❌ Invalid (too many records)"
                
                logger.info(f"  {symbol}: {resampled_count} intervals (max expected: {expected_max}) {status}")

def main():
    """Main entry point for local testing"""
    parser = argparse.ArgumentParser(description='Local Fibonacci Resampling Test')
    parser.add_argument('--intervals', nargs='*', type=int, help='Specific intervals to process (e.g., 3 5 8)')
    parser.add_argument('--database-url', type=str, help='Database connection URL')
    parser.add_argument('--show-results', action='store_true', help='Show detailed results')
    parser.add_argument('--validate', action='store_true', help='Validate data integrity')
    
    args = parser.parse_args()
    
    try:
        # Initialize local resampler
        resampler = LocalFibonacciResampler(database_url=args.database_url)
        
        # Run resampling job
        job_stats = resampler.run_fibonacci_resampling_job(intervals=args.intervals)
        
        # Show results if requested
        if args.show_results:
            resampler.show_results(intervals=args.intervals)
        
        # Validate data if requested
        if args.validate:
            resampler.validate_data_integrity()
        
        # Log final statistics
        logger.info("\n" + "="*60)
        logger.info("LOCAL FIBONACCI RESAMPLING TEST SUMMARY")
        logger.info("="*60)
        logger.info(f"Intervals Processed: {job_stats['intervals_processed']}")
        logger.info(f"Total Records: {job_stats['total_records']}")
        logger.info(f"Errors: {job_stats['errors']}")
        logger.info(f"Duration: {job_stats['duration_seconds']:.2f} seconds")
        logger.info("="*60)
        
        # Return success
        return 0 if job_stats['errors'] == 0 else 1
        
    except Exception as e:
        logger.error(f"Fatal error in local Fibonacci resampling test: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    print(f"\n🎯 Test completed with exit code: {exit_code}")
    if exit_code == 0:
        print("✅ All tests passed! Ready for AWS deployment.")
    else:
        print("❌ Tests failed. Check logs above.")
    
    sys.exit(exit_code)
