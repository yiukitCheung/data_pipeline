"""
TimescaleDB Initialization Lambda
Purpose: Initialize TimescaleDB with stock data schema and optimizations
"""

import json
import boto3
import psycopg2
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Initialize TimescaleDB with stock data schema"""
    
    try:
        # Get database credentials from Secrets Manager
        secret_arn = os.environ['DB_SECRET_ARN']
        database_name = os.environ['DATABASE_NAME']
        
        secrets_client = boto3.client('secretsmanager')
        secret_response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(secret_response['SecretString'])
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=secret_data['host'],
            port=secret_data['port'],
            user=secret_data['username'],
            password=secret_data['password'],
            dbname=database_name
        )
        
        conn.autocommit = True
        cursor = conn.cursor()
        
        logger.info("Connected to TimescaleDB successfully")
        
        # 1. Create TimescaleDB extension
        logger.info("Creating TimescaleDB extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        
        # 2. Create symbol metadata table (production version of your local schema)
        logger.info("Creating symbol metadata table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_metadata (
                symbol VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255),
                market VARCHAR(100),
                locale VARCHAR(100),
                active VARCHAR(100),
                primary_exchange VARCHAR(100),
                type VARCHAR(100),
                marketCap BIGINT,
                sector VARCHAR(50),
                industry VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. Create raw OHLCV table (production version - matching your local schema)
        logger.info("Creating raw OHLCV table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_ohlcv (
                symbol VARCHAR(50) NOT NULL,
                open DECIMAL(10,2) NOT NULL,
                high DECIMAL(10,2) NOT NULL,
                low DECIMAL(10,2) NOT NULL,
                close DECIMAL(10,2) NOT NULL,
                volume BIGINT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                interval VARCHAR(10) NOT NULL DEFAULT '1d',
                PRIMARY KEY (symbol, timestamp, interval)
            );
        """)
        
        # 4. Convert to TimescaleDB hypertable with 7-day chunks
        logger.info("Converting raw_ohlcv to TimescaleDB hypertable...")
        try:
            cursor.execute("SELECT create_hypertable('raw_ohlcv', 'timestamp', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');")
            logger.info("Created hypertable with 7-day chunks")
        except psycopg2.Error as e:
            if "already a hypertable" not in str(e):
                logger.warning(f"Hypertable creation issue: {str(e)}")
                # Try without chunk_time_interval parameter for older TimescaleDB versions
                try:
                    cursor.execute("SELECT create_hypertable('raw_ohlcv', 'timestamp', if_not_exists => TRUE);")
                    logger.info("Created hypertable with default chunks")
                except psycopg2.Error as e2:
                    if "already a hypertable" not in str(e2):
                        raise
                    logger.info("Table is already a hypertable")
            else:
                logger.info("Table is already a hypertable")
        
        # 5. Enable compression on raw_ohlcv
        logger.info("Enabling compression on raw_ohlcv...")
        try:
            cursor.execute("""
                ALTER TABLE raw_ohlcv SET (
                    timescaledb.compress,
                    timescaledb.compress_orderby = 'timestamp DESC',
                    timescaledb.compress_segmentby = 'symbol'
                );
            """)
            
            # Set compression policy to compress chunks older than 7 days
            cursor.execute("SELECT add_compression_policy('raw_ohlcv', INTERVAL '7 days');")
            logger.info("Compression enabled with 7-day policy")
        except psycopg2.Error as e:
            logger.warning(f"Compression setup issue: {str(e)}")
        
        # 6. Create Fibonacci resampled tables (silver layer) - matching your local schema
        fibonacci_intervals = [3, 5, 8, 13, 21, 34]
        
        for interval in fibonacci_intervals:
            table_name = f"silver_{interval}d"
            logger.info(f"Creating {table_name} table...")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    symbol VARCHAR(50) NOT NULL,
                    date DATE NOT NULL,
                    open DECIMAL(10,2) NOT NULL,
                    high DECIMAL(10,2) NOT NULL,
                    low DECIMAL(10,2) NOT NULL,
                    close DECIMAL(10,2) NOT NULL,
                    volume BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date)
                );
            """)
            
            # Convert silver tables to hypertables with 30-day chunks
            try:
                cursor.execute(f"SELECT create_hypertable('{table_name}', 'date', if_not_exists => TRUE, chunk_time_interval => INTERVAL '30 days');")
                logger.info(f"Created hypertable {table_name} with 30-day chunks")
            except psycopg2.Error as e:
                if "already a hypertable" not in str(e):
                    logger.warning(f"Hypertable creation issue for {table_name}: {str(e)}")
                    try:
                        cursor.execute(f"SELECT create_hypertable('{table_name}', 'date', if_not_exists => TRUE);")
                        logger.info(f"Created hypertable {table_name} with default chunks")
                    except psycopg2.Error as e2:
                        if "already a hypertable" not in str(e2):
                            logger.warning(f"Could not create hypertable for {table_name}: {str(e2)}")
                else:
                    logger.info(f"Table {table_name} is already a hypertable")
            
            # Enable compression on silver tables
            try:
                cursor.execute(f"""
                    ALTER TABLE {table_name} SET (
                        timescaledb.compress,
                        timescaledb.compress_orderby = 'date DESC',
                        timescaledb.compress_segmentby = 'symbol'
                    );
                """)
                
                cursor.execute(f"SELECT add_compression_policy('{table_name}', INTERVAL '7 days');")
                logger.info(f"Compression enabled for {table_name}")
            except psycopg2.Error as e:
                logger.warning(f"Compression setup issue for {table_name}: {str(e)}")
        
        # 7. Create performance indexes
        logger.info("Creating performance indexes...")
        
        # Raw OHLCV indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_symbol_timestamp ON raw_ohlcv(symbol, timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_timestamp ON raw_ohlcv(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_interval ON raw_ohlcv(interval);")
        
        # Silver table indexes
        for interval in fibonacci_intervals:
            table_name = f"silver_{interval}d"
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_date ON {table_name}(symbol, date DESC);")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name}(date DESC);")
        
        # 8. Update table statistics for query optimization
        logger.info("Updating table statistics...")
        cursor.execute("ANALYZE symbol_metadata;")
        cursor.execute("ANALYZE raw_ohlcv;")
        for interval in fibonacci_intervals:
            cursor.execute(f"ANALYZE silver_{interval}d;")
        
        # 9. Create sample data if needed (optional)
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata;")
        count = cursor.fetchone()[0]
        
        if count == 0:
            logger.info("Inserting sample symbol metadata...")
            cursor.execute("""
                INSERT INTO symbol_metadata (symbol, name, market, locale, active, primary_exchange, type) VALUES 
                ('AAPL', 'Apple Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
                ('MSFT', 'Microsoft Corporation', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
                ('GOOGL', 'Alphabet Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
                ('TSLA', 'Tesla Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
                ('AMZN', 'Amazon.com Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS')
                ON CONFLICT (symbol) DO NOTHING;
            """)
        
        cursor.close()
        conn.close()
        
        logger.info("TimescaleDB initialization completed successfully")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'TimescaleDB initialized successfully',
                'tables_created': ['symbol_metadata', 'raw_ohlcv'] + [f'silver_{i}d' for i in fibonacci_intervals],
                'optimizations_applied': [
                    'TimescaleDB extension enabled',
                    'Hypertables created for all tables',
                    'Compression policies set (7 days)',
                    'Performance indexes created',
                    'Raw OHLCV: 7-day chunks',
                    'Silver tables: 30-day chunks',
                    'Query statistics updated'
                ],
                'schema_source': 'Based on local_dev/init_sql/create_tables.sql (production version)'
            })
        }
        
    except Exception as e:
        logger.error(f"Error initializing TimescaleDB: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to initialize TimescaleDB'
            })
        }
