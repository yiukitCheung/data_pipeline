"""
Aurora Serverless client for database operations
"""

import boto3
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from decimal import Decimal

from ..models.data_models import OHLCVData, BatchProcessingJob, TechnicalIndicator

logger = logging.getLogger(__name__)


class AuroraClient:
    """Client for Aurora Serverless v2 PostgreSQL database operations"""
    
    def __init__(self, cluster_arn: str, secret_arn: str, database_name: str):
        self.cluster_arn = cluster_arn
        self.secret_arn = secret_arn
        self.database_name = database_name
        self.rds_client = boto3.client('rds-data')
    
    def execute_query(self, sql: str, parameters: List[Dict] = None) -> Dict[str, Any]:
        """Execute a SQL query using RDS Data API"""
        try:
            params = {
                'resourceArn': self.cluster_arn,
                'secretArn': self.secret_arn,
                'database': self.database_name,
                'sql': sql
            }
            
            if parameters:
                params['parameters'] = parameters
            
            response = self.rds_client.execute_statement(**params)
            return response
            
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            raise
    
    def get_active_symbols(self) -> List[str]:
        """Get list of active symbols from symbol_metadata table"""
        sql = """
        SELECT symbol 
        FROM symbol_metadata 
        WHERE is_active = true
        ORDER BY symbol
        """
        
        try:
            response = self.execute_query(sql)
            symbols = []
            
            if 'records' in response:
                for record in response['records']:
                    if record and len(record) > 0:
                        symbol_value = record[0]
                        if 'stringValue' in symbol_value:
                            symbols.append(symbol_value['stringValue'])
            
            logger.info(f"Retrieved {len(symbols)} active symbols")
            return symbols
            
        except Exception as e:
            logger.error(f"Error getting active symbols: {str(e)}")
            raise
    
    def insert_ohlcv_data(self, ohlcv_data: List[OHLCVData]) -> int:
        """Insert OHLCV data into the raw table"""
        if not ohlcv_data:
            return 0
        
        # Prepare batch insert
        sql = """
        INSERT INTO raw (timestamp, symbol, open, high, low, close, volume, interval)
        VALUES (:timestamp, :symbol, :open, :high, :low, :close, :volume, :interval)
        ON CONFLICT (timestamp, symbol, interval) 
        DO UPDATE SET 
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            interval = EXCLUDED.interval
        """
        
        try:
            records_inserted = 0
            
            # Process in batches to avoid API limits
            batch_size = 100
            for i in range(0, len(ohlcv_data), batch_size):
                batch = ohlcv_data[i:i + batch_size]
                
                # Execute batch insert using transaction
                parameters = []
                for ohlcv in batch:
                    parameters.append([
                        {'name': 'timestamp', 'value': {'timestampValue': ohlcv.timestamp.isoformat()}},
                        {'name': 'symbol', 'value': {'stringValue': ohlcv.symbol}},
                        {'name': 'open', 'value': {'doubleValue': float(ohlcv.open)}},
                        {'name': 'high', 'value': {'doubleValue': float(ohlcv.high)}},
                        {'name': 'low', 'value': {'doubleValue': float(ohlcv.low)}},
                        {'name': 'close', 'value': {'doubleValue': float(ohlcv.close)}},
                        {'name': 'volume', 'value': {'longValue': ohlcv.volume}},
                        {'name': 'interval', 'value': {'stringValue': ohlcv.interval}}
                    ])
                
                # Use batch execute for better performance
                response = self.rds_client.batch_execute_statement(
                    resourceArn=self.cluster_arn,
                    secretArn=self.secret_arn,
                    database=self.database_name,
                    sql=sql,
                    parameterSets=parameters
                )
                
                batch_inserted = len(batch)
                records_inserted += batch_inserted
                logger.info(f"Inserted batch of {batch_inserted} records")
            
            logger.info(f"Total records inserted: {records_inserted}")
            return records_inserted
            
        except Exception as e:
            logger.error(f"Error inserting OHLCV data: {str(e)}")
            raise
    
    def insert_batch_job_metadata(self, batch_job: BatchProcessingJob):
        """Insert batch job metadata for monitoring"""
        sql = """
        INSERT INTO batch_jobs (
            job_id, job_type, status, start_time, end_time, 
            symbols_processed, records_processed, error_message
        ) VALUES (
            :job_id, :job_type, :status, :start_time, :end_time,
            :symbols_processed, :records_processed, :error_message
        )
        ON CONFLICT (job_id) 
        DO UPDATE SET 
            status = EXCLUDED.status,
            end_time = EXCLUDED.end_time,
            symbols_processed = EXCLUDED.symbols_processed,
            records_processed = EXCLUDED.records_processed,
            error_message = EXCLUDED.error_message
        """
        
        parameters = [
            {'name': 'job_id', 'value': {'stringValue': batch_job.job_id}},
            {'name': 'job_type', 'value': {'stringValue': batch_job.job_type}},
            {'name': 'status', 'value': {'stringValue': batch_job.status}},
            {'name': 'start_time', 'value': {'timestampValue': batch_job.start_time.isoformat()}},
            {'name': 'end_time', 'value': {'timestampValue': batch_job.end_time.isoformat() if batch_job.end_time else None}},
            {'name': 'symbols_processed', 'value': {'stringValue': json.dumps(batch_job.symbols_processed)}},
            {'name': 'records_processed', 'value': {'longValue': batch_job.records_processed}},
            {'name': 'error_message', 'value': {'stringValue': batch_job.error_message or ''}}
        ]
        
        try:
            self.execute_query(sql, parameters)
            logger.info(f"Stored batch job metadata: {batch_job.job_id}")
            
        except Exception as e:
            logger.error(f"Error storing batch job metadata: {str(e)}")
            raise
    
    def get_latest_data_date(self, symbol: str = None) -> Optional[date]:
        """Get the latest data date for a symbol or all symbols"""
        if symbol:
            sql = """
            SELECT MAX(timestamp) as latest_date 
            FROM raw 
            WHERE symbol = :symbol
            """
            parameters = [{'name': 'symbol', 'value': {'stringValue': symbol}}]
        else:
            sql = """
            SELECT MAX(timestamp) as latest_date 
            FROM raw
            """
            parameters = None
        
        try:
            response = self.execute_query(sql, parameters)
            
            if 'records' in response and response['records']:
                record = response['records'][0]
                if record and len(record) > 0:
                    date_value = record[0]
                    if 'stringValue' in date_value:
                        return datetime.fromisoformat(date_value['stringValue']).date()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest data date: {str(e)}")
            raise
    
    def execute_resampling_query(self, interval: int, start_date: date = None) -> int:
        """Execute resampling query for a specific interval"""
        
        # Base resampling SQL (similar to your DuckDB version)
        sql = f"""
        WITH numbered AS (
            SELECT *,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp) AS rn
            FROM raw
            WHERE date >= COALESCE(:start_date, '1900-01-01'::date)
        ),
        grp AS (
            SELECT *,
                (rn - 1) / {interval} AS grp_id
            FROM numbered
        )
        INSERT INTO silver_{interval} (symbol, timestamp, open, high, low, close, volume)
        SELECT 
            symbol,
            MIN(timestamp) AS timestamp,
            (ARRAY_AGG(open ORDER BY date ASC))[1] AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
            SUM(volume) AS volume
        FROM grp
        GROUP BY symbol, grp_id
        ON CONFLICT (symbol, timestamp) 
        DO UPDATE SET 
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        """
        
        parameters = []
        if start_date:
            parameters.append({
                'name': 'start_date', 
                'value': {'stringValue': start_date.isoformat()}
            })
        
        try:
            response = self.execute_query(sql, parameters)
            records_processed = response.get('numberOfRecordsUpdated', 0)
            
            logger.info(f"Resampling interval {interval}: {records_processed} records processed")
            return records_processed
            
        except Exception as e:
            logger.error(f"Error executing resampling query for interval {interval}: {str(e)}")
            raise
    
    def get_symbol_data(self, symbol: str, start_date: date = None, end_date: date = None) -> List[Dict]:
        """Get symbol data for a date range"""
        sql = """
        SELECT timestamp, symbol, open, high, low, close, volume
        FROM raw
        WHERE symbol = :symbol
        """
        
        parameters = [{'name': 'symbol', 'value': {'stringValue': symbol}}]
        
        if start_date:
            sql += " AND timestamp >= :start_date"
            parameters.append({'name': 'start_date', 'value': {'stringValue': start_date.isoformat()}})
        
        if end_date:
            sql += " AND timestamp <= :end_date"
            parameters.append({'name': 'end_date', 'value': {'stringValue': end_date.isoformat()}})
        
        sql += " ORDER BY timestamp ASC"
        
        try:
            response = self.execute_query(sql, parameters)
            data = []
            
            if 'records' in response:
                for record in response['records']:
                    if len(record) >= 7:
                        data.append({
                            'timestamp': record[0].get('stringValue'),
                            'symbol': record[1].get('stringValue'),
                            'open': record[2].get('doubleValue'),
                            'high': record[3].get('doubleValue'),
                            'low': record[4].get('doubleValue'),
                            'close': record[5].get('doubleValue'),
                            'volume': record[6].get('longValue')
                        })
            
            return data
            
        except Exception as e:
            logger.error(f"Error getting symbol data for {symbol}: {str(e)}")
            raise
