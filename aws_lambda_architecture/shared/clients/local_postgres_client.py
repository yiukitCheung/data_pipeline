"""
Local PostgreSQL client for development and testing
This client uses direct psycopg2 connections instead of AWS RDS Data API
"""

import psycopg2
import logging
from typing import List, Optional, Tuple, Any
from datetime import datetime, date
from decimal import Decimal

from ..models.data_models import OHLCVData, BatchProcessingJob

logger = logging.getLogger(__name__)


class LocalPostgresClient:
    """Local PostgreSQL client for development environment"""
    
    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self._connection = None
    
    def get_connection(self):
        """Get or create database connection"""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(self.postgres_url)
        return self._connection
    
    def execute_query(self, sql: str, parameters: Tuple = None) -> List[Tuple]:
        """Execute a SQL query and return results"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            
            # Check if this is a SELECT query
            if sql.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                cursor.close()
                return results
            else:
                # For INSERT, UPDATE, DELETE
                conn.commit()
                cursor.close()
                return []
                
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            if self._connection:
                self._connection.rollback()
            raise
    
    def execute_transaction(self, queries: List[Tuple[str, Tuple]]) -> bool:
        """Execute multiple queries in a transaction"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            for sql, parameters in queries:
                if parameters:
                    cursor.execute(sql, parameters)
                else:
                    cursor.execute(sql)
            
            conn.commit()
            cursor.close()
            return True
            
        except Exception as e:
            logger.error(f"Error executing transaction: {str(e)}")
            if self._connection:
                self._connection.rollback()
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
            results = self.execute_query(sql)
            return [row[0] for row in results]
        except Exception as e:
            logger.warning(f"Error getting active symbols: {e}")
            return []
    
    def insert_symbol_metadata(self, symbols_data: List[dict]) -> bool:
        """Insert symbol metadata"""
        if not symbols_data:
            return True
        
        sql = """
        INSERT INTO symbol_metadata (symbol, name, market, type, primary_exchange, currency, is_active, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name,
            market = EXCLUDED.market,
            type = EXCLUDED.type,
            primary_exchange = EXCLUDED.primary_exchange,
            currency = EXCLUDED.currency,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at
        """
        
        try:
            queries = []
            for symbol_data in symbols_data:
                queries.append((sql, (
                    symbol_data.get('symbol'),
                    symbol_data.get('name', ''),
                    symbol_data.get('market', 'stocks'),
                    symbol_data.get('type', 'CS'),
                    symbol_data.get('primary_exchange', ''),
                    symbol_data.get('currency', 'USD'),
                    symbol_data.get('is_active', True),
                    datetime.now()
                )))
            
            return self.execute_transaction(queries)
            
        except Exception as e:
            logger.error(f"Error inserting symbol metadata: {str(e)}")
            return False
    
    def insert_ohlcv_data(self, ohlcv_data: List[OHLCVData]) -> bool:
        """Insert OHLCV data into TimescaleDB-optimized raw_ohlcv table"""
        if not ohlcv_data:
            return True
        
        sql = """
        INSERT INTO raw_ohlcv (symbol, open, high, low, close, volume, timestamp, interval)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, timestamp, interval) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        """
        
        try:
            queries = []
            for data in ohlcv_data:
                queries.append((sql, (
                    data.symbol,           # %s - symbol
                    float(data.open),      # %s - open
                    float(data.high),      # %s - high  
                    float(data.low),       # %s - low
                    float(data.close),     # %s - close
                    data.volume,           # %s - volume
                    data.timestamp,        # %s - timestamp
                    data.interval          # %s - interval
                )))
            
            return self.execute_transaction(queries)
            
        except Exception as e:
            logger.error(f"Error inserting OHLCV data: {str(e)}")
            return False
    
    def insert_batch_job_metadata(self, job: BatchProcessingJob) -> bool:
        """Insert batch job metadata"""
        sql = """
        INSERT INTO batch_jobs (job_id, job_type, symbols, start_date, end_date, status, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_id) DO UPDATE SET
            status = EXCLUDED.status,
            metadata = EXCLUDED.metadata,
            created_at = EXCLUDED.created_at
        """
        
        try:
            import json
            self.execute_query(sql, (
                job.job_id,
                job.job_type,
                job.symbols,
                job.start_date,
                job.end_date,
                job.status,
                json.dumps(job.metadata),
                job.created_at
            ))
            return True
            
        except Exception as e:
            logger.error(f"Error inserting batch job metadata: {str(e)}")
            return False
    
    def close(self):
        """Close database connection"""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
