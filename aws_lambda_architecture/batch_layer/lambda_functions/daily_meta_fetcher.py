"""
AWS Lambda function for daily metadata updating
Updates symbol metadata including market cap, sector, and industry information
"""

import json
import boto3
import logging
import time
import yfinance as yf
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import os
from curl_cffi import requests

# Import shared utilities
import sys
sys.path.append('/opt/python')  # Lambda layer path
from shared.clients.polygon_client import PolygonClient
from shared.clients.rds_timescale_client import RDSTimescaleClient
from shared.models.data_models import BatchProcessingJob

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for daily metadata updating
    
    Event can contain:
    - symbols: List of symbols to update (optional, defaults to all active)
    - batch_size: Number of symbols to process per batch (default: 20)
    - force: Boolean to force execution
    """
    
    try:
        # Initialize clients
        polygon_client = PolygonClient(api_key=os.environ['POLYGON_API_KEY'])
        rds_client = RDSTimescaleClient(
            secret_arn=os.environ['RDS_SECRET_ARN']
        )
        
        # Initialize enhanced session for Yahoo Finance
        yf_session = requests.Session(impersonate="chrome")
        yf_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }) 
        
        # Parse event parameters
        symbols = event.get('symbols', None)  # None means update all active symbols
        batch_size = int(event.get('batch_size', '20'))  # Smaller batches for metadata to avoid rate limits
        force_execution = event.get('force', False)
        
        # Create batch job record
        job_id = f"daily-metadata-{datetime.utcnow().strftime('%Y%m%d')}-{int(datetime.utcnow().timestamp())}"
        batch_job = BatchProcessingJob(
            job_id=job_id,
            job_type='DAILY_METADATA',
            status='RUNNING',
            start_time=datetime.utcnow(),
            symbols_processed=[],
            records_processed=0
        )
        
        logger.info(f"Starting daily metadata update, job_id: {job_id}")
        
        # Get symbols to process
        if symbols is None:
            symbols = rds_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from RDS TimescaleDB")
        else:
            logger.info(f"Processing specified {len(symbols)} symbols")
        
        batch_job.symbols_processed = symbols
        total_updated = 0
        
        # Process symbols in smaller batches to respect rate limits
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logger.info(f"Processing metadata batch {i//batch_size + 1}: {len(batch_symbols)} symbols")
            
            try:
                # Fetch and update metadata for batch
                metadata_list = fetch_metadata_batch(batch_symbols, polygon_client, yf_session)
                
                if metadata_list:
                    # Store in RDS TimescaleDB
                    records_updated = rds_client.insert_metadata_batch(metadata_list)
                    total_updated += records_updated
                    
                    logger.info(f"Updated {records_updated} metadata records for batch")
                else:
                    logger.warning(f"No metadata returned for batch: {batch_symbols}")
                
                # Add delay between batches to respect rate limits (especially Yahoo Finance)
                if i + batch_size < len(symbols):  # Don't delay after the last batch
                    time.sleep(2)  # 2 second delay between batches
                        
            except Exception as e:  
                logger.error(f"Error processing metadata batch {batch_symbols}: {str(e)}")
                # Continue with next batch rather than failing entire job
                continue
        
        # Update job status
        batch_job.status = 'COMPLETED'
        batch_job.end_time = datetime.utcnow()
        batch_job.records_processed = total_updated
        
        # Store job metadata (optional - for monitoring)
        store_job_metadata(rds_client, batch_job)
        
        logger.info(f"Completed daily metadata update. Total updated: {total_updated}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Daily metadata update completed successfully',
                'job_id': job_id,
                'symbols_processed': len(symbols),
                'records_updated': total_updated,
                'execution_time_seconds': (batch_job.end_time - batch_job.start_time).total_seconds()
            })
        }
        
    except Exception as e:
        logger.error(f"Fatal error in daily metadata fetcher: {str(e)}")
        
        # Update job status to failed
        if 'batch_job' in locals():
            batch_job.status = 'FAILED'
            batch_job.end_time = datetime.utcnow()
            batch_job.error_message = str(e)
            store_job_metadata(rds_client, batch_job)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Daily metadata update failed',
                'message': str(e)
            })
        }


def fetch_metadata_batch(symbols: List[str], polygon_client: PolygonClient, yf_session) -> List[Dict[str, Any]]:
    """
    Fetch metadata for a batch of symbols from Polygon and Yahoo Finance
    """
    metadata_list = []
    
    for symbol in symbols:
        try:
            # Fetch base metadata from Polygon
            meta_data = polygon_client.fetch_meta(ticker=symbol)
            
            if meta_data:
                # Add delay before Yahoo Finance requests to avoid rate limiting
                time.sleep(1.0)  # 1 second delay per symbol
                
                # Enhance with Yahoo Finance data (market cap, sector, industry)
                try:
                    ticker = yf.Ticker(symbol, session=yf_session)
                    info = ticker.info
                    
                    if info:
                        meta_data["marketCap"] = info.get("marketCap", 0)
                        meta_data["sector"] = info.get("sector", None)
                        meta_data["industry"] = info.get("industry", None)
                    else:
                        meta_data["marketCap"] = 0
                        meta_data["sector"] = None
                        meta_data["industry"] = None
                        
                except Exception as yf_error:
                    logger.warning(f"Yahoo Finance error for {symbol}: {str(yf_error)}")
                    # Use fallback values if Yahoo Finance fails
                    meta_data["marketCap"] = 0
                    meta_data["sector"] = None
                    meta_data["industry"] = None
                
                metadata_list.append(meta_data)
                logger.debug(f"Fetched metadata for {symbol}")
            else:
                logger.warning(f"No metadata returned for {symbol}")
                
        except Exception as e:
            logger.error(f"Error fetching metadata for {symbol}: {str(e)}")
            continue
    
    return metadata_list


def store_job_metadata(rds_client: RDSTimescaleClient, batch_job: BatchProcessingJob):
    """
    Store batch job metadata for monitoring
    """
    try:
        rds_client.insert_batch_job_metadata(batch_job)
    except Exception as e:
        logger.error(f"Error storing job metadata: {str(e)}")
        # Don't fail the main job for metadata storage issues