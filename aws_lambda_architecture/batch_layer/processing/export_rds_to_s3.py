"""
Export RDS PostgreSQL data directly to S3 Bronze Layer
This replaces the migration script - exports directly from RDS to new structure
"""

import psycopg2
import boto3
import pandas as pd
import logging
from datetime import datetime
import os
import sys
import time
import json
from botocore.exceptions import ClientError
import dotenv
dotenv.load_dotenv()
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
RDS_ENDPOINT = os.environ.get('RDS_HOST', 'dev-batch-postgres.czxi9iwguczt.ca-west-1.rds.amazonaws.com')
RDS_DB_NAME = os.environ.get('RDS_DATABASE', 'condvest')
RDS_USERNAME = os.environ.get('RDS_USER', 'postgres')
RDS_PASSWORD = os.environ.get('RDS_PASSWORD', '')

S3_BUCKET = os.environ.get('S3_BUCKET', 'dev-condvest-datalake')
S3_PREFIX = 'bronze/raw_ohlcv'
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ca-west-1')


class RDSToS3Exporter:
    """Export RDS data directly to S3 bronze layer"""
    
    def __init__(self, checkpoint_file='export_checkpoint.json'):
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        self.conn = None
        self.cursor = None
        self.checkpoint_file = checkpoint_file
        self.completed_symbols = set()
        self.rate_limit_delay = 0.5  # 500ms delay between uploads (prevent throttling)
        
        # Load checkpoint if exists
        self._load_checkpoint()
        
        logger.info(f"✅ Initialized RDS to S3 Exporter")
        logger.info(f"   RDS: {RDS_ENDPOINT}/{RDS_DB_NAME}")
        logger.info(f"   S3: s3://{S3_BUCKET}/{S3_PREFIX}/")
        if self.completed_symbols:
            logger.info(f"   📋 Resuming from checkpoint: {len(self.completed_symbols)} symbols already exported")
    
    def _load_checkpoint(self):
        """Load checkpoint from file"""
        try:
            if os.path.exists(self.checkpoint_file):
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.completed_symbols = set(data.get('completed_symbols', []))
                logger.info(f"📋 Loaded checkpoint: {len(self.completed_symbols)} symbols completed")
        except Exception as e:
            logger.warning(f"⚠️  Could not load checkpoint: {str(e)}")
            self.completed_symbols = set()
    
    def _save_checkpoint(self, symbol):
        """Save checkpoint after each successful symbol"""
        try:
            self.completed_symbols.add(symbol)
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'completed_symbols': list(self.completed_symbols),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"⚠️  Could not save checkpoint: {str(e)}")
    
    def connect_rds(self):
        """Connect to RDS PostgreSQL"""
        try:
            logger.info(f"📡 Connecting to RDS...")
            self.conn = psycopg2.connect(
                host=RDS_ENDPOINT,
                database=RDS_DB_NAME,
                user=RDS_USERNAME,
                password=RDS_PASSWORD,
                port=5432
            )
            self.cursor = self.conn.cursor()
            logger.info(f"✅ Connected to RDS successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to RDS: {str(e)}")
            return False
    
    def get_symbol_list(self):
        """Get list of all symbols in RDS"""
        try:
            query = "SELECT DISTINCT symbol FROM raw_ohlcv ORDER BY symbol"
            self.cursor.execute(query)
            symbols = [row[0] for row in self.cursor.fetchall()]
            logger.info(f"✅ Found {len(symbols)} symbols in RDS")
            return symbols
        except Exception as e:
            logger.error(f"❌ Error getting symbol list: {str(e)}")
            return []
    
    def export_symbol(self, symbol: str, max_retries=3) -> bool:
        """Export one symbol's data to S3 with retry logic"""
        
        for attempt in range(max_retries):
            try:
                # Query all data for this symbol
                query = """
                SELECT symbol, open, high, low, close, volume, timestamp, interval
                FROM raw_ohlcv
                WHERE symbol = %s
                ORDER BY timestamp
                """
                
                # Read into pandas DataFrame
                df = pd.read_sql_query(query, self.conn, params=(symbol,))
                
                if len(df) == 0:
                    logger.warning(f"⚠️  No data for {symbol}")
                    return False
                
                # Write to parquet file in /tmp
                temp_path = f"/tmp/{symbol}_data.parquet"
                df.to_parquet(temp_path, compression='snappy', index=False)
                
                # Upload to S3 with retry
                s3_key = f"{S3_PREFIX}/symbol={symbol}/data.parquet"
                
                try:
                    self.s3_client.upload_file(
                        temp_path,
                        S3_BUCKET,
                        s3_key
                    )
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code == 'SlowDown' or error_code == 'ServiceUnavailable':
                        # S3 throttling - increase delay and retry
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # Exponential backoff
                            logger.warning(f"⚠️  S3 throttling for {symbol}, waiting {wait_time}s... (attempt {attempt+1}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                    raise
                
                # Get file size
                file_size = os.path.getsize(temp_path)
                
                # Clean up temp file
                os.remove(temp_path)
                
                logger.info(f"   ✅ {symbol}: {len(df):,} records ({file_size / 1024:.1f} KB)")
                
                # Rate limiting - add delay to prevent throttling
                time.sleep(self.rate_limit_delay)
                
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️  Error exporting {symbol} (attempt {attempt+1}/{max_retries}): {str(e)}")
                    time.sleep((attempt + 1) * 2)  # Exponential backoff
                    continue
                else:
                    logger.error(f"   ❌ Failed to export {symbol} after {max_retries} attempts: {str(e)}")
                    return False
        
        return False
    
    def export_all(self, batch_size: int = 100):
        """Export all symbols from RDS to S3"""
        logger.info("=" * 70)
        logger.info("EXPORTING RDS DATA TO S3 BRONZE LAYER (WITH CHECKPOINTING)")
        logger.info("=" * 70)
        
        # Get all symbols
        all_symbols = self.get_symbol_list()
        if not all_symbols:
            logger.error("❌ No symbols found in RDS")
            return False
        
        # Filter out already completed symbols
        symbols = [s for s in all_symbols if s not in self.completed_symbols]
        
        total_symbols = len(all_symbols)
        already_done = len(self.completed_symbols)
        remaining = len(symbols)
        success_count = already_done
        fail_count = 0
        
        if already_done > 0:
            logger.info(f"\n📋 Checkpoint Status:")
            logger.info(f"   Already completed: {already_done} symbols")
            logger.info(f"   Remaining: {remaining} symbols")
            logger.info(f"   Total: {total_symbols} symbols\n")
        else:
            logger.info(f"\n📦 Exporting {total_symbols} symbols...")
        
        logger.info(f"   Rate limit: {self.rate_limit_delay}s delay between uploads")
        logger.info(f"   Progress updates: every {batch_size} symbols\n")
        
        start_time = time.time()
        
        # Export each symbol
        for idx, symbol in enumerate(symbols, 1):
            actual_idx = already_done + idx  # Account for already completed
            
            success = self.export_symbol(symbol)
            
            if success:
                success_count += 1
                self._save_checkpoint(symbol)  # Save progress after each success
            else:
                fail_count += 1
            
            # Progress update
            if idx % batch_size == 0 or idx == remaining:
                progress = (actual_idx / total_symbols) * 100
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining_time = (remaining - idx) / rate if rate > 0 else 0
                
                logger.info(f"\n📊 Progress: {actual_idx}/{total_symbols} ({progress:.1f}%)")
                logger.info(f"   Success: {success_count}, Failed: {fail_count}")
                logger.info(f"   Speed: {rate:.2f} symbols/sec")
                logger.info(f"   Estimated time remaining: {remaining_time/60:.1f} minutes\n")
        
        logger.info("=" * 70)
        logger.info("🎉 EXPORT COMPLETED!")
        logger.info("=" * 70)
        logger.info(f"✅ Successfully exported: {success_count} symbols")
        logger.info(f"❌ Failed: {fail_count} symbols")
        logger.info(f"📦 Location: s3://{S3_BUCKET}/{S3_PREFIX}/")
        logger.info(f"⏱️  Total time: {(time.time() - start_time)/60:.1f} minutes")
        logger.info("=" * 70)
        
        return fail_count == 0
    
    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("✅ Closed RDS connection")


def main():
    """Main execution function"""
    
    # Check environment variables
    if not RDS_PASSWORD:
        print("❌ Error: RDS_PASSWORD environment variable not set")
        print("\nPlease set:")
        print("  export RDS_HOST=your-endpoint.rds.amazonaws.com")
        print("  export RDS_USER=postgres")
        print("  export RDS_PASSWORD=your_password")
        print("  export RDS_DATABASE=condvest")
        sys.exit(1)
    
    # Initialize exporter
    exporter = RDSToS3Exporter()
    
    try:
        # Connect to RDS
        if not exporter.connect_rds():
            sys.exit(1)
        
        # Export all data
        success = exporter.export_all(batch_size=100)
        
        if success:
            logger.info("✅ Export completed successfully!")
            sys.exit(0)
        else:
            logger.error("⚠️  Export completed with some errors")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Export interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
        
    finally:
        exporter.close()


if __name__ == "__main__":
    main()

