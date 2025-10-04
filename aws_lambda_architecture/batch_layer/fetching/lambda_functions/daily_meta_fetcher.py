"""
AWS Lambda function for daily metadata updating (Simplified - Polygon API only)
Updates symbol metadata from Polygon API (no yfinance/pandas dependencies)
Uses asyncio for parallel fetching (10x faster!)
"""

import json
import boto3
import logging
import os
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Import shared utilities (no layer dependencies)
from shared.clients.polygon_client import PolygonClient
from shared.clients.rds_timescale_client import RDSTimescaleClient
from shared.clients.fmp_client import FMPClient
from shared.models.data_models import BatchProcessingJob

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def fetch_metadata_async(session: aiohttp.ClientSession, symbol: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Async fetch metadata for a single symbol from Polygon API
    """
    try:
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        params = {'apiKey': api_key}
        
        async with session.get(url, params=params) as response:
            if response.status != 200:
                logger.warning(f"API request failed for {symbol} with status {response.status}")
                return None
            
            data = await response.json()
            result = data.get('results', None)
            
            if result:
                # Transform to database schema
                metadata = {
                    'symbol': result.get('ticker', symbol),
                    'name': result.get('name'),
                    'market': result.get('market'),
                    'locale': result.get('locale'),
                    'active': str(result.get('active', False)),
                    'primary_exchange': result.get('primary_exchange'),
                    'type': result.get('type'),
                    'marketCap': result.get('market_cap'),
                    'industry': result.get('sic_description'),
                    'description': result.get('description')
                }
                logger.info(f"Fetched metadata for {symbol}")
                return metadata
            return None
            
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {str(e)}")
        return None


async def fetch_batch_async(symbols: List[str], api_key: str, max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch metadata for multiple symbols concurrently
    
    Args:
        symbols: List of symbols to fetch
        api_key: Polygon API key
        max_concurrent: Maximum concurrent requests (default 10)
    
    Returns:
        List of metadata dictionaries
    """
    connector = aiohttp.TCPConnector(limit=max_concurrent)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch_metadata_async(session, symbol, api_key) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        metadata_list = []
        failed_symbols = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Exception for {symbol}: {str(result)}")
                failed_symbols.append(symbol)
            elif result is not None:
                metadata_list.append(result)
            else:
                failed_symbols.append(symbol)
        
        if failed_symbols:
            logger.warning(f"Failed to fetch {len(failed_symbols)} symbols")
        
        return metadata_list


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
        # Get the API keys from the secrets manager
        polygon_api_key = json.loads(polygon_secret['SecretString'])['POLYGON_API_KEY']
        
        # Initialize clients
        polygon_client = PolygonClient(api_key=polygon_api_key)
        rds_client = RDSTimescaleClient(secret_arn=os.environ['RDS_SECRET_ARN'])
        
        # Parse event parameters
        symbols = event.get('symbols', None)
        batch_size = int(event.get('batch_size', '128'))
        
        # Create batch job record
        job_id = f"daily-metadata-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        logger.info(f"Starting metadata update job: {job_id}")
        
        # Determine if the market is open
        market_status = polygon_client.get_market_status()
        if market_status['market'] == 'closed':
            logger.info(f"Skipping execution - market is closed")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Skipping execution - market is closed'})
            }
            
        # Get symbols to process
        if (symbols is None) and (len(rds_client.get_active_symbols()) != 0):
            symbols = rds_client.get_active_symbols()
            logger.info(f"Fetched {len(symbols)} active symbols from database")
        elif symbols is None:
            symbols = polygon_client.get_active_symbols()  # Fetch ALL symbols (no limit)
            logger.info(f"No active symbols found in database, fetched {len(symbols)} active symbols from Polygon API")
        else:
            logger.info(f"Processing {len(symbols)} specified symbols")
        
        total_updated = 0
        failed_count = 0
        
        # Process symbols in batches using async fetching (10 concurrent requests per batch)
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch_symbols)} symbols (async)")
            
            try:
                # Fetch entire batch concurrently (10x faster!)
                batch_metadata = asyncio.run(fetch_batch_async(
                    batch_symbols, 
                    polygon_api_key, 
                    max_concurrent=10
                ))
                
                logger.info(f"Fetched {len(batch_metadata)} metadata records from Polygon API")
                
                # Insert batch to database
                if batch_metadata:
                    try:
                        rds_client.insert_metadata_batch(batch_metadata)
                        total_updated += len(batch_metadata)
                        logger.info(f"Inserted {len(batch_metadata)} metadata records to database")
                    except Exception as e:
                        logger.error(f"Error inserting batch: {str(e)}")
                        failed_count += len(batch_metadata)
                else:
                    logger.warning(f"No metadata fetched for batch {i//batch_size + 1}")
                    
            except Exception as e:
                logger.error(f"Error processing batch {i//batch_size + 1}: {str(e)}")
                failed_count += len(batch_symbols)
        
        # Log completion
        logger.info(f"Job completed: {total_updated} updated, {failed_count} failed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'completed',
                'job_id': job_id,
                'symbols_processed': total_updated,
                'symbols_failed': failed_count,
                'message': f'Successfully updated {total_updated} symbols (async)'
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
