from daily_pipeline import bronze_pipeline
from make_silver_pipeline import silver_pipeline
from config.load_setting import load_setting

# Load settings
settings = load_setting()

# Create deployment with schedule and timezone
deployment = bronze_pipeline.serve(
    name="bronze-pipeline-deployment",
    parameters={"settings": settings},
    work_queue_name="default",  # This is the default queue in the bronze-pipeline work pool
    schedule=({"cron": "00 16 * * 1-5", "timezone": "America/New_York"})  # 4:00 PM ET weekdays
)

# # Create deployment with schedule and timezone
# deployment = silver_pipeline.serve(
#     name="silver-pipeline-deployment",
#     parameters={"settings": settings},
#     work_queue_name="silver-pipeline",
#     schedule=({"cron": "05 16 * * 1-5", "timezone": "America/New_York"})  # 4:05 PM ET weekdays
# )

if __name__ == "__main__":
    deployment.apply()

