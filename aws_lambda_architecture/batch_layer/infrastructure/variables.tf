# ===============================================
# Batch Layer Variables
# ===============================================

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ca-west-1"
}

# Database Configuration
variable "database_name" {
  description = "Name of the database"
  type        = string
  default     = "condvest"
}

variable "postgres_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.8"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage in GB"
  type        = number
  default     = 100
}

variable "allow_public_access" {
  description = "Whether to allow public access to RDS (for initial setup)"
  type        = bool
  default     = true
}

variable "publicly_accessible" {
  description = "Whether the RDS instance is publicly accessible"
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Enable deletion protection for RDS"
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Whether to skip final snapshot on RDS deletion"
  type        = bool
  default     = true
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

# Batch Configuration
variable "batch_max_vcpus" {
  description = "Maximum vCPUs for Batch compute environment"
  type        = number
  default     = 32
}

variable "batch_job_vcpus" {
  description = "vCPUs for individual Batch job"
  type        = string
  default     = "2"
}

variable "batch_job_memory" {
  description = "Memory for individual Batch job (MB)"
  type        = string
  default     = "4096"
}

variable "fibonacci_intervals" {
  description = "Comma-separated list of Fibonacci intervals to resample"
  type        = string
  default     = "3,5,8,13,21,34"
}

# Scheduling
variable "daily_schedule_expression" {
  description = "EventBridge cron expression for daily data fetch"
  type        = string
  default     = "cron(5 21 * * ? *)"  # 4:05 PM EST (9:05 PM UTC)
}

variable "meta_schedule_expression" {
  description = "EventBridge cron expression for daily metadata fetch"
  type        = string
  default     = "cron(35 21 * * ? *)"  # 4:35 PM EST (9:35 PM UTC)
}

variable "enable_scheduling" {
  description = "Whether to enable scheduled data fetching"
  type        = bool
  default     = true
}

# External APIs
variable "polygon_api_key_secret_arn" {
  description = "ARN of the Polygon API key secret in AWS Secrets Manager"
  type        = string
}

# Monitoring
variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

variable "enable_cost_monitoring" {
  description = "Whether to enable cost monitoring and alerting"
  type        = bool
  default     = true
}

# Lambda Layers
variable "lambda_layer_arns" {
  description = "List of Lambda Layer ARNs for heavy dependencies"
  type        = list(string)
  default     = []
}
