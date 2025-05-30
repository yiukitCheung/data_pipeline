# Create the work pool  
prefect work-pool create bronze-pipeline

# Deploy the deployment
prefect deploy flows/daily_pipeline.py:bronze_pipeline -n bronze-pipeline-deployment -p bronze-pipeline --cron "00 16 * * 1-5" --timezone "America/New_York"

# Start the worker
prefect worker start -p bronze-pipeline