from prefect import flow, task
from prefect import get_run_logger
from prefect.tasks import task_input_hash
from prefect.cache_policies import NO_CACHE

from config.load_setting import load_setting
settings = load_setting()

from process.core import Resampler

@flow(name="silver-pipeline")
def silver_pipeline():
    """Make silver data from raw data by resampling to different intervals"""
    logger = get_run_logger()
    logger.info("Starting silver pipeline")
    
    try:
        # Initialize resampler
        resampler = Resampler(settings)
        
        # Process/update resampled data
        resampler.run()
        
        logger.info("Silver pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Error in silver pipeline: {str(e)}")
        raise


