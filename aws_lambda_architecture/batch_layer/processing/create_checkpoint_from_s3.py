"""
Create checkpoint file from existing S3 data
Scans S3 to find what symbols are already exported
"""

import boto3
import json
import os
from datetime import datetime

S3_BUCKET = os.environ.get('S3_BUCKET', 'dev-condvest-datalake')
S3_PREFIX = 'bronze/raw_ohlcv'
AWS_REGION = os.environ.get('AWS_DEFAULT_REGION', 'ca-west-1')

def create_checkpoint_from_s3():
    """Scan S3 and create checkpoint file"""
    
    print("=" * 70)
    print("CREATING CHECKPOINT FROM S3")
    print("=" * 70)
    print(f"Scanning: s3://{S3_BUCKET}/{S3_PREFIX}/")
    print()
    
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    
    completed_symbols = []
    
    # List all objects in S3 bronze layer
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(
        Bucket=S3_BUCKET,
        Prefix=f"{S3_PREFIX}/symbol="
    )
    
    for page in pages:
        if 'Contents' not in page:
            continue
        
        for obj in page['Contents']:
            key = obj['Key']
            # Extract symbol from path: bronze/raw_ohlcv/symbol=AAPL/data.parquet
            if '/symbol=' in key and key.endswith('/data.parquet'):
                symbol = key.split('/symbol=')[1].split('/')[0]
                completed_symbols.append(symbol)
                
                if len(completed_symbols) % 100 == 0:
                    print(f"   Found {len(completed_symbols)} symbols...")
    
    # Remove duplicates and sort
    completed_symbols = sorted(list(set(completed_symbols)))
    
    print(f"\n✅ Found {len(completed_symbols)} symbols already in S3")
    
    # Create checkpoint file
    checkpoint_data = {
        'completed_symbols': completed_symbols,
        'last_updated': datetime.now().isoformat(),
        'created_from': 's3_scan'
    }
    
    checkpoint_file = 'export_checkpoint.json'
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    
    print(f"✅ Created checkpoint file: {checkpoint_file}")
    print(f"\nSample symbols:")
    for symbol in completed_symbols[:10]:
        print(f"   - {symbol}")
    if len(completed_symbols) > 10:
        print(f"   ... and {len(completed_symbols) - 10} more")
    
    print("\n" + "=" * 70)
    print("🎉 CHECKPOINT CREATED!")
    print("=" * 70)
    print(f"Now run: python export_rds_to_s3.py")
    print(f"It will skip these {len(completed_symbols)} symbols")
    print("=" * 70)

if __name__ == "__main__":
    create_checkpoint_from_s3()

