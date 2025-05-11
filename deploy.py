from daily_flows.daily_pipeline import bronze_pipeline
from config.load_setting import load_setting
from prefect.server.schemas.schedules import CronSchedule

# Load settings
settings = load_setting()


# Local file system block
from prefect.filesystems import LocalFileSystem
local_file_system_block = LocalFileSystem.load("local-data-pipeline")

# Create deployment with schedule and timezone
deployment = bronze_pipeline.serve(
    name="bronze-pipeline-deployment",
    parameters={"settings": settings},
    schedule={"cron": "30 16 * * 1-5", "timezone": "America/New_York"}  # 4:30 PM ET weekdays
)

