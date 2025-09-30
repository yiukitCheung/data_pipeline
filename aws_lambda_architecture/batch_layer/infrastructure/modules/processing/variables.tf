# ===============================================
# Processing Module Variables
# ===============================================

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# Networking
variable "subnet_ids" {
  description = "List of subnet IDs for Batch compute environment"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for Batch compute environment"
  type        = list(string)
}

variable "batch_security_group_id" {
  description = "Security group ID for Batch compute environment"
  type        = string
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

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

# Database Configuration
variable "database_name" {
  description = "Database name"
  type        = string
}

variable "database_port" {
  description = "Database port"
  type        = number
  default     = 5432
}

variable "cloudwatch_log_group_name" {
  description = "CloudWatch log group name"
  type        = string
}

# Scheduling
variable "resampling_schedule_expression" {
  description = "EventBridge cron expression for daily resampling"
  type        = string
  default     = "cron(5 21 * * ? *)"  # 4:05 PM EST (9:05 PM UTC)
}

# IAM Role ARNs
variable "batch_service_role_arn" {
  description = "ARN of the Batch service role"
  type        = string
}

variable "batch_execution_role_arn" {
  description = "ARN of the Batch execution role"
  type        = string
}

variable "batch_job_role_arn" {
  description = "ARN of the Batch job role"
  type        = string
}

variable "eventbridge_role_arn" {
  description = "ARN of the EventBridge role for triggering Batch jobs"
  type        = string
}

variable "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  type        = string
}
