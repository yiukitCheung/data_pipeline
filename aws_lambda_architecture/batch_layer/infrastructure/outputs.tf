# ===============================================
# Batch Layer Outputs
# ===============================================

# Database Outputs
output "postgres_endpoint" {
  description = "PostgreSQL database endpoint"
  value       = module.database.postgres_endpoint
}

output "postgres_port" {
  description = "PostgreSQL database port"
  value       = module.database.postgres_port
}

output "postgres_secret_arn" {
  description = "ARN of the PostgreSQL credentials secret"
  value       = module.database.postgres_secret_arn
}

output "postgres_security_group_id" {
  description = "Security group ID for PostgreSQL database"
  value       = module.database.postgres_security_group_id
}

# Lambda Function Outputs
output "daily_ohlcv_fetcher_function_arn" {
  description = "ARN of the daily OHLCV fetcher Lambda function"
  value       = module.fetching.daily_ohlcv_fetcher_function_arn
}

output "daily_ohlcv_fetcher_function_name" {
  description = "Name of the daily OHLCV fetcher Lambda function"
  value       = module.fetching.daily_ohlcv_fetcher_function_name
}

output "daily_meta_fetcher_function_arn" {
  description = "ARN of the daily metadata fetcher Lambda function"
  value       = module.fetching.daily_meta_fetcher_function_arn
}

output "daily_meta_fetcher_function_name" {
  description = "Name of the daily metadata fetcher Lambda function"
  value       = module.fetching.daily_meta_fetcher_function_name
}

# Batch Processing Outputs
output "ecr_repository_url" {
  description = "URL of the ECR repository for fibonacci resampler"
  value       = module.processing.ecr_repository_url
}

output "batch_job_queue_name" {
  description = "Name of the Batch job queue"
  value       = module.processing.batch_job_queue_name
}

output "batch_job_definition_name" {
  description = "Name of the Batch job definition"
  value       = module.processing.batch_job_definition_name
}

# Scheduling Outputs
output "daily_ohlcv_schedule_rule_arn" {
  description = "ARN of the daily OHLCV fetch EventBridge rule"
  value       = module.fetching.daily_ohlcv_schedule_rule_arn
}

output "daily_meta_schedule_rule_arn" {
  description = "ARN of the daily metadata fetch EventBridge rule"
  value       = module.fetching.daily_meta_schedule_rule_arn
}

output "daily_resampling_rule_arn" {
  description = "ARN of the daily resampling EventBridge rule"
  value       = module.processing.daily_resampling_rule_arn
}

# Security Group Outputs
output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  value       = module.shared.lambda_security_group_id
}

output "batch_security_group_id" {
  description = "Security group ID for Batch compute environment"
  value       = module.shared.batch_security_group_id
}

# IAM Role Outputs
output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = module.shared.lambda_execution_role_arn
}

output "batch_service_role_arn" {
  description = "ARN of the Batch service role"
  value       = module.shared.batch_service_role_arn
}

# Log Group Outputs
output "ohlcv_lambda_log_group_name" {
  description = "CloudWatch log group name for OHLCV Lambda"
  value       = module.fetching.ohlcv_lambda_log_group_name
}

output "meta_lambda_log_group_name" {
  description = "CloudWatch log group name for metadata Lambda"
  value       = module.fetching.meta_lambda_log_group_name
}

output "batch_log_group_name" {
  description = "CloudWatch log group name for Batch jobs"
  value       = module.processing.batch_log_group_name
}
