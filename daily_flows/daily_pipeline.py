from dotenv import load_dotenv
import os
load_dotenv()  # Load environment variables first

from prefect import flow, task
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_fetch.fetch_batch_raw import BatchDataExtractor
from ingestion.ingest_raw import StockDataIngestor
from data_fetch.fetch_meta import MetaDataExtractor
from ingestion.ingest_meta import StockMetaIngestor
from processing.make_silver import Processor
from processing.make_gold import SignalsGenerator   
from config.load_setting import load_setting
import logging

logger = logging.getLogger(__name__)

@flow(name="daily-pipeline")
def daily_pipeline(settings):
    """Main pipeline flow"""
    try:
        # # Submit batch tasks concurrently
        # batch_extractor_future = run_batch_extractor.submit(settings)
        # batch_ingestor_future = run_batch_ingestor.submit(settings)
        
        # # Check results
        # if batch_extractor_future.state.is_failed():
        #     raise Exception("Batch extractor failed")
        # if batch_ingestor_future.state.is_failed():
        #     raise Exception("Batch ingestor failed")
        
        # Run the silver and gold tasks
        make_silver(settings)
        
        # Run the gold task
        # make_gold(settings)             
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise

@task
def run_batch_extractor(settings):
    batch_extractor = BatchDataExtractor(settings)
    batch_extractor.run()
    
@task
def run_batch_ingestor(settings):
    ingestor = StockDataIngestor(settings)
    ingestor.run()

@task
def run_meta_extractor(settings):
    meta_extractor = MetaDataExtractor(settings)
    meta_extractor.run()

@task
def run_meta_ingestor(settings):
    meta_ingestor = StockMetaIngestor(settings)
    meta_ingestor.run()

@task
def make_silver(settings):
    make_silver = Processor(settings)
    make_silver.run()
    
@task
def make_gold(settings):
    make_gold = SignalsGenerator(settings)
    make_gold.run()
    
if __name__ == "__main__":
    settings = load_setting(mode="development")
    daily_pipeline(settings)