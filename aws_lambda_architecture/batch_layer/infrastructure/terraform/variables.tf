# Terraform Variables for Batch Layer
# Purpose: Cost-efficient daily processing and Fibonacci resampling

# Environment Configuration
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region for batch layer resources"
  type        = string
  default     = "us-east-1"
}

# Networking
variable "vpc_id" {
  description = "VPC ID for batch layer resources"
  type        = string
  default     = null  # Will be looked up via data source
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for batch jobs"
  type        = list(string)
  default     = []  # Will be looked up via data source
}

# Database Configuration (TimescaleDB on RDS PostgreSQL)
variable "database_name" {
  description = "Database name for TimescaleDB instance"
  type        = string
  default     = "condvest"
}

variable "db_username" {
  description = "Master username for TimescaleDB instance"
  type        = string
  default     = "condvest_admin"
}

variable "db_instance_class" {
  description = "RDS instance class for cost optimization"
  type        = string
  default     = "db.t3.micro"  # $15-20/month vs Aurora's $50-100/month
}

variable "db_allocated_storage" {
  description = "Initial allocated storage in GB"
  type        = number
  default     = 20  # Start small, auto-scale as needed
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage in GB (auto-scaling)"
  type        = number
  default     = 100  # Scale up to 100GB automatically
}

variable "postgres_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.8"  # Latest available in ca-west-1
}

variable "backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
  default     = 7  # 1 week retention for cost optimization
}

variable "enable_performance_insights" {
  description = "Enable Performance Insights"
  type        = bool
  default     = false  # Disable to save cost in dev/staging
}

variable "monitoring_interval" {
  description = "Enhanced monitoring interval in seconds"
  type        = number
  default     = 0  # Disable enhanced monitoring to save cost
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot when deleting (dev/staging only)"
  type        = bool
  default     = true  # Set to false in production
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = false  # Set to true in production
}

# Lambda Configuration (Bronze Layer)
variable "lambda_runtime" {
  description = "Lambda runtime for daily OHLCV fetcher"
  type        = string
  default     = "python3.10"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 900  # 15 minutes
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB"
  type        = number
  default     = 512
}

# AWS Batch Configuration (Silver Layer)
variable "batch_compute_type" {
  description = "Batch compute environment type"
  type        = string
  default     = "FARGATE_SPOT"  # Cost optimization

  validation {
    condition     = contains(["FARGATE", "FARGATE_SPOT"], var.batch_compute_type)
    error_message = "Batch compute type must be FARGATE or FARGATE_SPOT."
  }
}

variable "batch_max_vcpus" {
  description = "Maximum vCPUs for batch compute environment"
  type        = number
  default     = 256
}

variable "batch_job_vcpu" {
  description = "vCPUs for Fibonacci resampling job"
  type        = string
  default     = "1.0"  # 1 vCPU sufficient for most workloads
}

variable "batch_job_memory" {
  description = "Memory (MB) for Fibonacci resampling job"
  type        = string
  default     = "2048"  # 2GB memory
}

variable "batch_job_timeout" {
  description = "Job timeout in seconds"
  type        = number
  default     = 3600  # 1 hour
}

# Fibonacci Resampling Configuration
variable "fibonacci_intervals" {
  description = "Fibonacci intervals to process"
  type        = list(number)
  default     = [3, 5, 8, 13, 21, 34]  # Your Fibonacci sequence
}

variable "fibonacci_lookback_days" {
  description = "Days to look back for Fibonacci resampling"
  type        = number
  default     = 300  # ~1 year of trading days
}

# External APIs
variable "polygon_api_key_secret_arn" {
  description = "ARN of secret containing Polygon API key"
  type        = string
}

# Monitoring and Logging
variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = false  # Cost optimization
}

# Scheduling
variable "daily_schedule_expression" {
  description = "EventBridge schedule for daily OHLCV fetch and processing"
  type        = string
  default     = "cron(5 21 * * ? *)"  # 4:05 PM EST weekdays (9:05 PM UTC)
}

variable "enable_scheduling" {
  description = "Enable automatic scheduling of daily jobs"
  type        = bool
  default     = true
}

# Cost Optimization
variable "spot_allocation_strategy" {
  description = "Spot allocation strategy for cost optimization"
  type        = string
  default     = "SPOT_CAPACITY_OPTIMIZED"
}

variable "spot_max_price_percentage" {
  description = "Maximum spot price as percentage of on-demand"
  type        = number
  default     = 50  # 50% of on-demand price
}

# Security
variable "enable_encryption" {
  description = "Enable encryption for batch job data"
  type        = bool
  default     = true
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional)"
  type        = string
  default     = null  # Use default AWS managed key
}

# Feature Flags
variable "enable_job_notifications" {
  description = "Enable SNS notifications for job status"
  type        = bool
  default     = false  # Keep simple for MVP
}

variable "enable_batch_insights" {
  description = "Enable AWS Batch compute environment insights"
  type        = bool
  default     = false  # Cost optimization
}

# ECR Configuration
variable "ecr_image_tag" {
  description = "Docker image tag for Fibonacci resampler"
  type        = string
  default     = "latest"
}

variable "force_new_deployment" {
  description = "Force new deployment when image changes"
  type        = bool
  default     = false
}

# Missing variables for batch configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

variable "enable_cost_monitoring" {
  description = "Enable cost monitoring alarms"
  type        = bool
  default     = true
}

variable "batch_job_vcpus" {
  description = "vCPUs for batch job"
  type        = string
  default     = "1.0"
}
