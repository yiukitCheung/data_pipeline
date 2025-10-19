"""
Check RDS PostgreSQL data
Quick script to verify what data exists in RDS
"""

import psycopg2
import os
from datetime import datetime
import dotenv
dotenv.load_dotenv()
# RDS Configuration (update these)
RDS_ENDPOINT = os.environ.get('RDS_HOST', 'dev-batch-postgres.czxi9iwguczt.ca-west-1.rds.amazonaws.com')
RDS_DB_NAME = os.environ.get('RDS_DATABASE', 'condvest')
RDS_USERNAME = os.environ.get('RDS_USER', 'postgres')
RDS_PASSWORD = os.environ.get('RDS_PASSWORD', '')

def check_rds_data():
    """Check what data exists in RDS"""
    
    print("=" * 70)
    print("CHECKING RDS DATA")
    print("=" * 70)
    print(f"Endpoint: {RDS_ENDPOINT}")
    print(f"Database: {RDS_DB_NAME}")
    print()
    
    try:
        # Connect to RDS
        conn = psycopg2.connect(
            host=RDS_ENDPOINT,
            database=RDS_DB_NAME,
            user=RDS_USERNAME,
            password=RDS_PASSWORD,
            port=5432
        )
        
        cursor = conn.cursor()
        
        # Check raw_ohlcv table
        print("📊 Checking raw_ohlcv table...")
        
        query = """
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT symbol) as unique_symbols,
            MIN(DATE(timestamp)) as earliest_date,
            MAX(DATE(timestamp)) as latest_date,
            pg_size_pretty(pg_total_relation_size('raw_ohlcv')) as table_size
        FROM raw_ohlcv
        """
        
        cursor.execute(query)
        result = cursor.fetchone()
        
        print(f"\n✅ RDS Data Summary:")
        print(f"   Total Records: {result[0]:,}")
        print(f"   Unique Symbols: {result[1]:,}")
        print(f"   Date Range: {result[2]} to {result[3]}")
        print(f"   Table Size: {result[4]}")
        print()
        
        # Check sample symbols
        print("📋 Sample Symbols:")
        cursor.execute("""
            SELECT symbol, COUNT(*) as record_count, 
                   MIN(DATE(timestamp)) as earliest, 
                   MAX(DATE(timestamp)) as latest
            FROM raw_ohlcv 
            GROUP BY symbol 
            ORDER BY symbol 
            LIMIT 10
        """)
        
        samples = cursor.fetchall()
        for symbol, count, earliest, latest in samples:
            print(f"   {symbol}: {count:,} records ({earliest} to {latest})")
        
        print()
        print("=" * 70)
        print("✅ RDS DATA EXISTS! We can export from RDS to S3!")
        print("=" * 70)
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error checking RDS: {str(e)}")
        print("\nPlease set environment variables:")
        print("  export RDS_HOST=your-endpoint.rds.amazonaws.com")
        print("  export RDS_USER=postgres")
        print("  export RDS_PASSWORD=your_password")
        print("  export RDS_DATABASE=condvest")
        return False


if __name__ == "__main__":
    check_rds_data()

