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

from tools.polygon_client import PolygonTools
import logging

from datetime import datetime
from zoneinfo import ZoneInfo
import time
from datetime import timedelta
logger = logging.getLogger(__name__)

@flow(name="daily-pipeline")
def daily_pipeline(settings):
    """Main pipeline flow"""
    try:
        # Submit batch tasks concurrently
        batch_extractor_future = run_batch_extractor.submit(settings)
        batch_ingestor_future = run_batch_ingestor.submit(settings)
        
        # Check results
        if batch_extractor_future.state.is_failed():
            raise Exception("Batch extractor failed")
        if batch_ingestor_future.state.is_failed():
            raise Exception("Batch ingestor failed")
                
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise

def reset_mode_pipeline(settings):
    """Reset mode pipeline"""
    try:
        # Step 1. Ingest meta data
        meta_extractor_future = run_meta_extractor.submit(settings)
        meta_ingestor_future = run_meta_ingestor.submit(settings)
        
        # Step 2. Ingest raw data
        batch_extractor_future = run_batch_extractor.submit(settings)
        batch_ingestor_future = run_batch_ingestor.submit(settings)
        
        # Check results
        if meta_extractor_future.state.is_failed():
            raise Exception("Meta extractor failed")
        if meta_ingestor_future.state.is_failed():
            raise Exception("Meta ingestor failed")
        if batch_extractor_future.state.is_failed():
            raise Exception("Batch extractor failed")
        if batch_ingestor_future.state.is_failed():
            raise Exception("Batch ingestor failed")
        
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
    


if __name__ == "__main__":
    polygon_client = PolygonTools(api_key=os.getenv('POLYGON_API_KEY'))

    # Continuous daily run loop
    while True:
        now = datetime.now(ZoneInfo("America/New_York"))
        target_hour = 9  # 9 AM
        target_minute = 30

        # If it's before 9:30 AM ET
        if now.hour < target_hour or (now.hour == target_hour and now.minute < target_minute):
            time_diff_minutes = ((target_hour * 60 + target_minute) - (now.hour * 60 + now.minute))
            if time_diff_minutes > 120:
                sleep_duration = 7200  # Sleep 2 hours
            elif time_diff_minutes > 60:
                sleep_duration = 300  # Sleep 5 minutes
            else:
                sleep_duration = 60  # Sleep 1 minute

            print(f"Waiting for 9:30 AM ET... sleeping {sleep_duration // 60} minutes.")
            time.sleep(sleep_duration)
            continue

        # After 9:30 AM, check market status
        market_status = polygon_client.get_market_status()
        if market_status == 'open':
            settings = load_setting(status="development")
            if settings.get("mode") == "production":
                if now.hour == 16 and now.minute >= 30:
                    daily_pipeline(settings)
            elif settings.get("mode") == "reset":
                if now.hour == 16 and now.minute >= 30:
                    reset_mode_pipeline(settings)

        # Wait until next day
        print("Pipeline completed for the day. Sleeping until next run...")
        now = datetime.now(ZoneInfo("America/New_York"))
        next_run = datetime.combine(now.date(), datetime.min.time(), tzinfo=ZoneInfo("America/New_York")) + timedelta(days=1, hours=9, minutes=30)
        sleep_seconds = (next_run - now).total_seconds() - 10
        time.sleep(sleep_seconds)