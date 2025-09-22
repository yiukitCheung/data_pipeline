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

# Aurora Database Configuration
variable "aurora_cluster_arn" {
  description = "Aurora cluster ARN for data storage"
  type        = string
}

variable "aurora_secret_arn" {
  description = "Aurora secret ARN for database credentials"
  type        = string
}

variable "database_name" {
  description = "Database name in Aurora cluster"
  type        = string
  default     = "condvest"
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
  default     = "cron(15 21 * * MON-FRI *)"  # 9:15 PM EST weekdays (15 min after 4 PM market close)
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
