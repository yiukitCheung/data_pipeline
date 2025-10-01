"""
AWS Lambda function for daily metadata updating (Simplified - Polygon API only)
Updates symbol metadata from Polygon API (no yfinance/pandas dependencies)
"""

import json
import boto3
import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Import shared utilities (no layer dependencies)
from shared.clients.polygon_client import PolygonClient
from shared.clients.rds_timescale_client import RDSTimescaleClient
from shared.models.data_models import BatchProcessingJob

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for daily metadata updating using Polygon API only
    
    Event can contain:
    - symbols: List of symbols to update (optional, defaults to all active)
    - batch_size: Number of symbols to process per batch (default: 50)
    - force: Boolean to force execution
    """
    
    try:
        # Get Polygon API key from Secrets Manager
        secrets_client = boto3.client('secretsmanager')
        polygon_secret = secrets_client.get_secret_value(
            SecretId=os.environ['POLYGON_API_KEY_SECRET_ARN']
        )
        polygon_api_key = json.loads(polygon_secret['SecretString'])['POLYGON_API_KEY']
        
        # Initialize clients
        polygon_client = PolygonClient(api_key=polygon_api_key)
        rds_client = RDSTimescaleClient(
            secret_arn=os.environ['RDS_SECRET_ARN']
        )
        
        # Parse event parameters
        symbols = event.get('symbols', None)
        batch_size = int(event.get('batch_size', '50'))
        force_execution = event.get('force', False)
        
        # Create batch job record
        job_id = f"daily-metadata-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        logger.info(f"Starting metadata update job: {job_id}")
        
        # Get symbols to process
        if (symbols is None) and (len(rds_client.get_active_symbols()) != 0):
            symbols = rds_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from database")
        elif symbols is None:
            symbols = polygon_client.get_active_symbols()
            logger.info(f"No active symbols found in database, fetched {len(symbols)} active symbols from Polygon API")
        else:
            logger.info(f"Processing {len(symbols)} specified symbols")
        
        total_updated = 0
        failed_symbols = []
        
        # Process symbols in batches
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_symbols)} symbols")
            
            for symbol in batch_symbols:
                try:
                    # Fetch metadata from Polygon only (no yfinance)
                    metadata = polygon_client.fetch_meta(ticker=symbol)
                    
                    if metadata:
                        # Store in database
                        rds_client.insert_metadata_batch([metadata])
                        total_updated += 1
                        
                        logger.debug(f"Updated metadata for {symbol}")
                    else:
                        logger.warning(f"No metadata returned for {symbol}")
                        failed_symbols.append(symbol)
                    
                    # Rate limiting - Polygon has 5 requests/minute limit on free tier
                    time.sleep(0.2)  # 5 requests per second max
                    
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {str(e)}")
                    failed_symbols.append(symbol)
            
            # Delay between batches
            if i + batch_size < len(symbols):
                logger.info("Pausing between batches...")
                time.sleep(2)
        
        # Log completion
        logger.info(f"Job completed: {total_updated} updated, {len(failed_symbols)} failed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'completed',
                'job_id': job_id,
                'symbols_processed': total_updated,
                'symbols_failed': len(failed_symbols),
                'failed_symbols': failed_symbols[:10] if failed_symbols else [],
                'message': f'Successfully updated {total_updated} symbols'
            })
        }
        
    except Exception as e:
        logger.error(f"Job failed with error: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            })
        }
