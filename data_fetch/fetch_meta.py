from kafka import KafkaProducer
import pandas as pd
from functools import partial
import json, logging, pytz, aiohttp, asyncio
from datetime import datetime
from dotenv import load_dotenv
from prefect import get_run_logger

import sys, os 
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import postgres_client, kafka_client, polygon_client
from datetime import datetime
from config.load_setting import load_setting

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

POSTGRES_URL = os.getenv('POSTGRES_URL')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
KAFKA_BROKER = os.getenv('KAFKA_BROKER')

class MetaDataExtractor:
    def __init__(self, settings):
        # Extract configs
        self.mode = settings['mode']
        self.current_date = pd.to_datetime("today").strftime('%Y-%m-%d')
        self.topic_names = settings['data_extract']['meta']['topic_names']
        self.table_name = settings['data_extract']['meta']['table_name']
        self.chunk_size = settings['data_extract']['meta']['chunk_size']
        # Initialize tools
        self.timescale_tool = postgres_client.PostgresTools(POSTGRES_URL)
        self.polygon_tool = polygon_client.PolygonTools(POLYGON_API_KEY)
        self.kafka_tool = kafka_client.KafkaTools()
        self.logger = get_run_logger()
        
        # Find all available symbols from polygon api
        self.symbols = self.polygon_tool.fetch_all_tickers()
        
        # Initialize async components
        self.semaphore = asyncio.Semaphore(100)  # Limit concurrent requests
        self.symbol_locks = {}  # Locks for each symbol
        self.session = None
        
        # Initialize Kafka producer
        try:
            # Delete and recreate topic if reset mode is enabled
            if self.mode == "reset":
                self.kafka_tool.delete_kafka_topics(self.topic_names, KAFKA_BROKER)
                self.kafka_tool.create_kafka_topic(self.topic_names, KAFKA_BROKER)
                self.logger.info(f"MetaDataExtractor: Recreated Kafka topic {self.topic_names}")

            self.batch_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda x: json.dumps(x).encode('utf-8')
            )
            self.logger.info(f"MetaDataExtractor: Kafka Producer connected to {KAFKA_BROKER}")
        except Exception as e:
            self.logger.error(f"MetaDataExtractor: Error initializing Kafka producer: {e}")
            raise e
        
    async def init_session(self):
        """Initialize aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _get_symbol_meta_async(self, symbol, max_retries=3):
        """Async version of fetching symbol metadata"""
        try:
            if symbol not in self.symbol_locks:
                self.symbol_locks[symbol] = asyncio.Lock()

            async with self.symbol_locks[symbol]:
                async with self.semaphore:
                    loop = asyncio.get_event_loop()
                    try:
                        # Fetch metadata using the polygon client
                        meta_data = await loop.run_in_executor(
                            None,
                            partial(self.polygon_tool.fetch_meta, ticker=symbol)
                        )
                        
                        if meta_data:
                            # Add timestamp to metadata
                            return meta_data, symbol
                        else:
                            self.logger.warning(f"MetaDataExtractor: No metadata returned for {symbol}")
                            return None, symbol
                            
                    except Exception as e:
                        if "Too Many Requests" in str(e):
                            self.logger.warning(f"Rate limited for {symbol}, waiting 30s")
                            await asyncio.sleep(30)
                            return None, symbol
                        self.logger.error(f"MetaDataExtractor: Error fetching metadata for {symbol}: {e}")
                        return None, symbol

        except Exception as e:
            self.logger.error(f"MetaDataExtractor: Error in async metadata fetch for {symbol}: {e}")
            return None, symbol

    async def _produce_meta_to_kafka_async(self, meta_data, symbol: str):
        """Async version of producing metadata to Kafka"""
        if not meta_data:
            return
        
        loop = asyncio.get_event_loop()
        
        try:
            # Create metadata record for kafka
            meta_record = {
                'symbol': symbol,
                'name': meta_data['name'],
                'market': meta_data['market'],
                'locale': meta_data['locale'],
                'active': meta_data['active'],
                'primary_exchange': meta_data['primary_exchange'],
                'type': meta_data['type']
            }
            
            # Use run_in_executor without timeout
            future = await loop.run_in_executor(
                None,
                lambda: self.batch_producer.send(self.topic_names, meta_record)
            )
            
            # Wait for acknowledgment without timeout
            await loop.run_in_executor(None, future.get)
            self.logger.info(f"Successfully sent metadata for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to send metadata for {symbol}: {e}")
            # Add to retry queue

    async def fetch_and_produce_meta_async(self):
        """Async version of fetching and producing metadata"""
        await self.init_session()
        
        try:
            # Process symbols in chunks to avoid overwhelming the API
            chunk_size = self.chunk_size
            chunks = [self.symbols[i:i + chunk_size] 
                    for i in range(0, len(self.symbols), chunk_size)]
            
            for chunk in chunks:
                # Process each chunk
                tasks = [
                    asyncio.create_task(self._get_symbol_meta_async(symbol))
                    for symbol in chunk
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results for this chunk
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"MetaDataExtractor: Task error: {result}")
                        continue
                    
                    meta_data, symbol = result
                    if meta_data is not None:
                        await self._produce_meta_to_kafka_async(meta_data, symbol)
                            
                # Add delay between chunks
                await asyncio.sleep(2)  # 2 second delay between chunks
                self.logger.info(f"MetaDataExtractor: Processed chunk of {len(chunk)} symbols")
                
        finally:
            await self.close_session()

    async def run_async(self):
        """Async version of run"""
        try:
            await self.fetch_and_produce_meta_async()
            self.logger.info("MetaDataExtractor: Metadata fetching complete")
        except Exception as e:
            self.logger.error(f"MetaDataExtractor error: {e}")
            raise

    def run(self):
        """Entry point with proper cleanup"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("MetaDataExtractor: Received interrupt signal")
        except Exception as e:
            self.logger.error(f"MetaDataExtractor: Fatal error: {e}")
        finally:
            # Ensure synchronous cleanup
            if hasattr(self, 'batch_producer') and self.batch_producer:
                try:
                    self.batch_producer.flush(timeout=30)
                    self.batch_producer.close(timeout=30)
                except Exception as e:
                    self.logger.error(f"MetaDataExtractor: Error during final cleanup: {e}")

    def batch_insert_metadata(self, table_name, records):
        # Deduplicate records by symbol
        unique_records = {}
        for record in records:
            symbol = record['symbol']
            unique_records[symbol] = record
        
        # Convert back to list
        deduplicated_records = list(unique_records.values())
        
        # Now perform the batch insert with deduplicated records
        # ... rest of your insert logic ...

if __name__ == "__main__":
    # Load Data Pipeline Configuration
    mode = 'development'
    settings = load_setting(mode)
    
    # Initialize and run the MetaDataExtractor
    meta_extractor = MetaDataExtractor(settings)
    meta_extractor.run()