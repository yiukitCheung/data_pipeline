"""
Migrate S3 Bronze Layer Data Structure

OLD: s3://bucket/public/raw_ohlcv/LOAD*.parquet (DMS export, no partitioning)
NEW: s3://bucket/bronze/raw_ohlcv/symbol=AAPL/date=2025-10-18.parquet (symbol-partitioned)

This script:
1. Reads all data from old DMS structure
2. Re-partitions by symbol and date
3. Writes to new bronze structure
4. Validates migration
5. Optionally backs up and deletes old files
"""

import boto3
import duckdb
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'dev-condvest-datalake')
OLD_PREFIX = 'public/raw_ohlcv'  # DMS export location
NEW_PREFIX = 'bronze/raw_ohlcv'  # New symbol-partitioned location
BACKUP_PREFIX = 'public/raw_ohlcv_backup'  # Backup location
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ca-west-1')


class S3BronzeMigrator:
    """Migrates S3 bronze layer from DMS structure to symbol-partitioned structure"""
    
    def __init__(self, s3_bucket: str):
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
        
        # Get AWS credentials from boto3 session
        session = boto3.Session()
        credentials = session.get_credentials()
        
        # Initialize DuckDB with S3 support
        self.duckdb_conn = duckdb.connect(':memory:')
        self.duckdb_conn.execute(f"SET s3_region='{AWS_REGION}'")
        
        # Set AWS credentials for DuckDB
        if credentials:
            self.duckdb_conn.execute(f"SET s3_access_key_id='{credentials.access_key}'")
            self.duckdb_conn.execute(f"SET s3_secret_access_key='{credentials.secret_key}'")
            if credentials.token:
                self.duckdb_conn.execute(f"SET s3_session_token='{credentials.token}'")
        
        self.duckdb_conn.execute("INSTALL httpfs")
        self.duckdb_conn.execute("LOAD httpfs")
        
        logger.info(f"✅ Initialized S3 Bronze Migrator")
        logger.info(f"   Bucket: {s3_bucket}")
        logger.info(f"   Old Path: s3://{s3_bucket}/{OLD_PREFIX}/")
        logger.info(f"   New Path: s3://{s3_bucket}/{NEW_PREFIX}/")
    
    def validate_old_data_exists(self) -> bool:
        """Check if old DMS data exists"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=OLD_PREFIX,
                MaxKeys=1
            )
            
            if 'Contents' in response:
                logger.info(f"✅ Found old DMS data in s3://{self.s3_bucket}/{OLD_PREFIX}/")
                return True
            else:
                logger.warning(f"⚠️  No data found in s3://{self.s3_bucket}/{OLD_PREFIX}/")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error checking old data: {str(e)}")
            return False
    
    def get_old_file_list(self) -> List[str]:
        """Get list of all parquet files in old structure"""
        logger.info(f"📋 Listing files in s3://{self.s3_bucket}/{OLD_PREFIX}/")
        
        files = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=self.s3_bucket,
            Prefix=OLD_PREFIX
        )
        
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith('.parquet'):
                    files.append(key)
                    logger.debug(f"  Found: {key}")
        
        logger.info(f"✅ Found {len(files)} parquet files to migrate")
        return files
    
    def read_old_data(self) -> pd.DataFrame:
        """Read all data from old DMS structure using DuckDB"""
        logger.info(f"📖 Reading data from old structure...")
        
        old_s3_path = f"s3://{self.s3_bucket}/{OLD_PREFIX}/*.parquet"
        
        try:
            # Create DuckDB view with column mapping (handle timestamp_1)
            # Use timestamp_1 as it's the actual data timestamp (timestamp is DMS migration tracking)
            query = f"""
            SELECT 
                symbol,
                open,
                high,
                low,
                close,
                volume,
                timestamp_1 as timestamp,  -- AWS DMS: actual data timestamp
                interval
            FROM read_parquet('{old_s3_path}')
            """
            
            df = self.duckdb_conn.execute(query).df()
            
            logger.info(f"✅ Read {len(df):,} records from old structure")
            logger.info(f"   Symbols: {df['symbol'].nunique():,}")
            logger.info(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error reading old data: {str(e)}")
            raise
    
    def write_new_structure(self, df: pd.DataFrame, dry_run: bool = False) -> Dict:
        """
        Write data to new symbol-partitioned structure
        
        OPTIMIZED: One file per symbol (all dates in one file)
        Path format: bronze/raw_ohlcv/symbol=AAPL/data.parquet
        """
        logger.info(f"📝 Writing data to new structure (dry_run={dry_run})...")
        
        # Stats
        stats = {
            'total_records': len(df),
            'symbols_count': df['symbol'].nunique(),
            'dates_count': pd.to_datetime(df['timestamp']).dt.date.nunique(),
            'files_written': 0,
            'bytes_written': 0
        }
        
        # Group by symbol only (one file per symbol)
        grouped = df.groupby('symbol')
        total_symbols = len(grouped)
        
        logger.info(f"   Will create {total_symbols:,} parquet files (one per symbol)")
        logger.info(f"   Average records per symbol: {len(df) / total_symbols:,.0f}")
        
        if dry_run:
            logger.info("🔍 DRY RUN - Not actually writing files")
            stats['files_written'] = total_symbols
            return stats
        
        # Write each symbol's data to one file
        for idx, (symbol, symbol_df) in enumerate(grouped, 1):
            # S3 key: bronze/raw_ohlcv/symbol=AAPL/data.parquet
            s3_key = f"{NEW_PREFIX}/symbol={symbol}/data.parquet"
            
            # Write to S3 using DuckDB
            try:
                temp_path = f"/tmp/{symbol}_data.parquet"
                symbol_df.to_parquet(temp_path, compression='snappy', index=False)
                
                # Upload to S3
                self.s3_client.upload_file(
                    temp_path,
                    self.s3_bucket,
                    s3_key
                )
                
                # Get file size
                file_size = os.path.getsize(temp_path)
                stats['bytes_written'] += file_size
                
                # Clean up temp file
                os.remove(temp_path)
                
                stats['files_written'] += 1
                
                if idx % 100 == 0 or idx == total_symbols:
                    progress = (idx / total_symbols) * 100
                    logger.info(f"   Progress: {idx}/{total_symbols} ({progress:.1f}%) - Latest: {symbol} ({len(symbol_df):,} records)")
                
            except Exception as e:
                logger.error(f"❌ Error writing {s3_key}: {str(e)}")
                # Continue with other files
                continue
        
        logger.info(f"✅ Migration completed!")
        logger.info(f"   Files written: {stats['files_written']:,}")
        logger.info(f"   Total size: {stats['bytes_written'] / (1024**3):.2f} GB")
        
        return stats
    
    def validate_migration(self) -> bool:
        """Validate that migration was successful"""
        logger.info(f"🔍 Validating migration...")
        
        try:
            # Read data from new structure
            new_s3_path = f"s3://{self.s3_bucket}/{NEW_PREFIX}/symbol=*/data.parquet"
            
            query = f"""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT symbol) as unique_symbols,
                MIN(timestamp) as earliest_date,
                MAX(timestamp) as latest_date
            FROM read_parquet('{new_s3_path}')
            """
            
            result = self.duckdb_conn.execute(query).df()
            
            logger.info(f"✅ New structure validation:")
            logger.info(f"   Records: {result['total_records'][0]:,}")
            logger.info(f"   Symbols: {result['unique_symbols'][0]:,}")
            logger.info(f"   Date range: {result['earliest_date'][0]} to {result['latest_date'][0]}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Validation failed: {str(e)}")
            return False
    
    def backup_old_files(self, dry_run: bool = False) -> bool:
        """Backup old files to backup location"""
        logger.info(f"💾 Backing up old files (dry_run={dry_run})...")
        
        try:
            files = self.get_old_file_list()
            
            if dry_run:
                logger.info(f"🔍 DRY RUN - Would backup {len(files)} files")
                return True
            
            for idx, old_key in enumerate(files, 1):
                # New backup key: public/raw_ohlcv_backup/LOAD*.parquet
                backup_key = old_key.replace(OLD_PREFIX, BACKUP_PREFIX)
                
                # Copy file
                self.s3_client.copy_object(
                    Bucket=self.s3_bucket,
                    CopySource={'Bucket': self.s3_bucket, 'Key': old_key},
                    Key=backup_key
                )
                
                if idx % 10 == 0 or idx == len(files):
                    progress = (idx / len(files)) * 100
                    logger.info(f"   Progress: {idx}/{len(files)} ({progress:.1f}%)")
            
            logger.info(f"✅ Backed up {len(files)} files to s3://{self.s3_bucket}/{BACKUP_PREFIX}/")
            return True
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {str(e)}")
            return False
    
    def delete_old_files(self, dry_run: bool = False) -> bool:
        """Delete old files after successful migration"""
        logger.info(f"🗑️  Deleting old files (dry_run={dry_run})...")
        
        try:
            files = self.get_old_file_list()
            
            if dry_run:
                logger.info(f"🔍 DRY RUN - Would delete {len(files)} files")
                return True
            
            # Confirm deletion
            logger.warning(f"⚠️  About to delete {len(files)} files from s3://{self.s3_bucket}/{OLD_PREFIX}/")
            logger.warning(f"⚠️  Make sure backup completed successfully!")
            
            # Delete in batches of 1000 (S3 limit)
            for i in range(0, len(files), 1000):
                batch = files[i:i+1000]
                objects = [{'Key': key} for key in batch]
                
                self.s3_client.delete_objects(
                    Bucket=self.s3_bucket,
                    Delete={'Objects': objects}
                )
                
                logger.info(f"   Deleted batch: {i+len(batch)}/{len(files)}")
            
            logger.info(f"✅ Deleted {len(files)} old files")
            return True
            
        except Exception as e:
            logger.error(f"❌ Deletion failed: {str(e)}")
            return False
    
    def run_migration(self, dry_run: bool = False, backup: bool = True, delete_old: bool = False):
        """Run complete migration process"""
        logger.info("=" * 70)
        logger.info("S3 BRONZE LAYER MIGRATION")
        logger.info("=" * 70)
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        logger.info(f"Backup: {backup}")
        logger.info(f"Delete Old: {delete_old}")
        logger.info("=" * 70)
        
        # Step 1: Validate old data exists
        if not self.validate_old_data_exists():
            logger.error("❌ No old data found, aborting migration")
            return False
        
        # Step 2: Read all old data
        try:
            df = self.read_old_data()
        except Exception as e:
            logger.error(f"❌ Failed to read old data: {str(e)}")
            return False
        
        # Step 3: Write to new structure
        stats = self.write_new_structure(df, dry_run=dry_run)
        logger.info(f"✅ Migration stats: {stats}")
        
        # Step 4: Validate migration (if not dry run)
        if not dry_run:
            if not self.validate_migration():
                logger.error("❌ Migration validation failed!")
                return False
        
        # Step 5: Backup old files (if requested)
        if backup and not dry_run:
            if not self.backup_old_files(dry_run=False):
                logger.error("❌ Backup failed! NOT deleting old files")
                return False
        
        # Step 6: Delete old files (if requested and backup succeeded)
        if delete_old and backup and not dry_run:
            if not self.delete_old_files(dry_run=False):
                logger.error("❌ Deletion failed!")
                return False
        
        logger.info("=" * 70)
        logger.info("🎉 MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        
        return True
    
    def close(self):
        """Close DuckDB connection"""
        self.duckdb_conn.close()
        logger.info("✅ Closed DuckDB connection")


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate S3 Bronze Layer Structure')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual changes)')
    parser.add_argument('--no-backup', action='store_true', help='Skip backup step')
    parser.add_argument('--delete-old', action='store_true', help='Delete old files after migration')
    parser.add_argument('--bucket', type=str, default=S3_BUCKET, help='S3 bucket name')
    
    args = parser.parse_args()
    
    # Initialize migrator
    migrator = S3BronzeMigrator(s3_bucket=args.bucket)
    
    try:
        # Run migration
        success = migrator.run_migration(
            dry_run=args.dry_run,
            backup=not args.no_backup,
            delete_old=args.delete_old
        )
        
        if success:
            logger.info("✅ Migration completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Migration failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
        
    finally:
        migrator.close()


if __name__ == "__main__":
    main()

