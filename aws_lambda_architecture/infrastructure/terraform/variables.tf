# ===============================================
# Variables for AWS Lambda Architecture
# ===============================================

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "condvest-data-pipeline"
}

# ===============================================
# Database Configuration
# ===============================================

variable "db_instance_class" {
  description = "Aurora Serverless v2 instance class"
  type        = string
  default     = "db.serverless"
}

variable "db_min_capacity" {
  description = "Minimum Aurora Serverless v2 capacity (ACUs)"
  type        = number
  default     = 0.5
}

variable "db_max_capacity" {
  description = "Maximum Aurora Serverless v2 capacity (ACUs)"
  type        = number
  default     = 8
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "condvest"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "condvest_admin"
}

# ===============================================
# Redis Configuration
# ===============================================

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes"
  type        = number
  default     = 1
}

# ===============================================
# Kinesis Configuration
# ===============================================

variable "kinesis_shard_count" {
  description = "Number of Kinesis shards"
  type        = number
  default     = 1
}

variable "kinesis_retention_period" {
  description = "Kinesis data retention period in hours"
  type        = number
  default     = 24
}

# ===============================================
# Lambda Configuration
# ===============================================

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 900
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 1024
}

# ===============================================
# DynamoDB Configuration
# ===============================================

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "tick_data_ttl_days" {
  description = "TTL for tick data in DynamoDB (days)"
  type        = number
  default     = 1
}

# ===============================================
# API Gateway Configuration
# ===============================================

variable "api_throttle_rate_limit" {
  description = "API Gateway throttle rate limit"
  type        = number
  default     = 1000
}

variable "api_throttle_burst_limit" {
  description = "API Gateway throttle burst limit"
  type        = number
  default     = 2000
}

# ===============================================
# External Services
# ===============================================

variable "polygon_api_key" {
  description = "Polygon.io API key"
  type        = string
  sensitive   = true
}

variable "allowed_origins" {
  description = "Allowed CORS origins for API Gateway"
  type        = list(string)
  default     = ["*"]
}

# ===============================================
# Monitoring Configuration
# ===============================================

variable "enable_xray_tracing" {
  description = "Enable X-Ray tracing for Lambda functions"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 14
}

# ===============================================
# Cost Optimization
# ===============================================

variable "enable_cost_optimization" {
  description = "Enable cost optimization features"
  type        = bool
  default     = true
}

variable "schedule_expression_batch" {
  description = "Cron expression for batch processing"
  type        = string
  default     = "cron(0 16 ? * MON-FRI *)"  # 4 PM EST weekdays
}
