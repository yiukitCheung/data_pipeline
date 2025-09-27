# Terraform Variables for Batch Layer
environment = "dev"
aws_region = "ca-west-1"
database_name = "condvest"

# Polygon API Key Secret ARN (replace with your actual ARN)
polygon_api_key_secret_arn = "arn:aws:secretsmanager:ca-west-1:471112909340:secret:prod/Condvest/PolygonAPI-iFAG4h"

# Database Configuration
db_instance_class = "db.t3.micro"
db_allocated_storage = 20
db_max_allocated_storage = 100

# Batch Configuration
batch_max_vcpus = 4
fibonacci_intervals = [3, 5, 8, 13, 21, 34]

# Monitoring
enable_cost_monitoring = true
cloudwatch_log_retention_days = 14
