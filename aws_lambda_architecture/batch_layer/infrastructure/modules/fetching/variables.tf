# ===============================================
# Fetching Module Variables
# ===============================================

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# Lambda Configuration
variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.11"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB"
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

# Networking
variable "subnet_ids" {
  description = "List of subnet IDs for Lambda VPC configuration"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  type        = string
}

# Database Configuration
variable "rds_secret_arn" {
  description = "ARN of the RDS credentials secret"
  type        = string
}

variable "database_name" {
  description = "Database name"
  type        = string
}

variable "rds_endpoint" {
  description = "RDS endpoint"
  type        = string
}

# External APIs
variable "polygon_api_key_secret_arn" {
  description = "ARN of the Polygon API key secret"
  type        = string
}

# Batch Processing
variable "batch_job_queue_name" {
  description = "AWS Batch job queue name for resampling"
  type        = string
}

variable "batch_job_definition_name" {
  description = "AWS Batch job definition name for Fibonacci resampling"
  type        = string
}

# Scheduling
variable "daily_schedule_expression" {
  description = "EventBridge cron expression for daily OHLCV fetch"
  type        = string
  default     = "cron(5 21 * * ? *)"  # 4:05 PM EST (9:05 PM UTC)
}

variable "meta_schedule_expression" {
  description = "EventBridge cron expression for daily metadata fetch"
  type        = string
  default     = "cron(35 21 * * ? *)"  # 4:35 PM EST (9:35 PM UTC)
}

variable "deployment_artifacts_path" {
  description = "Path to deployment artifacts (ZIP files)"
  type        = string
  default     = "../fetching/deployment_packages"
}

# IAM
variable "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  type        = string
}
