from daily_flows.daily_pipeline import bronze_pipeline
from config.load_setting import load_setting

# Load settings
settings = load_setting()

# Create deployment with schedule and timezone
deployment = bronze_pipeline.serve(
    name="bronze-pipeline-deployment",
    parameters={"settings": settings},
    work_queue_name="default",  # This is the default queue in the bronze-pipeline work pool
    schedule=({"cron": "30 16 * * 1-5", "timezone": "America/New_York"})  # 4:30 PM ET weekdays
)

if __name__ == "__main__":
    deployment.apply()

