# Terraform Outputs for Batch Layer
# Purpose: Export key resources for integration with other layers

# Database Outputs (TimescaleDB)
output "timescale_endpoint" {
  description = "TimescaleDB endpoint for stock data"
  value       = aws_db_instance.timescale.address
}

output "timescale_port" {
  description = "TimescaleDB port"
  value       = aws_db_instance.timescale.port
}

output "timescale_secret_arn" {
  description = "Secrets Manager ARN for TimescaleDB credentials"
  value       = aws_secretsmanager_secret.timescale_credentials.arn
}

output "database_name" {
  description = "Database name"
  value       = var.database_name
}

output "timescale_security_group_id" {
  description = "Security group ID for TimescaleDB"
  value       = aws_security_group.timescale.id
}

# Lambda Function Outputs (Bronze Layer)
output "daily_ohlcv_fetcher_function_arn" {
  description = "ARN of the daily OHLCV fetcher Lambda function"
  value       = aws_lambda_function.daily_ohlcv_fetcher.arn
}

output "daily_ohlcv_fetcher_function_name" {
  description = "Name of the daily OHLCV fetcher Lambda function"
  value       = aws_lambda_function.daily_ohlcv_fetcher.function_name
}

# AWS Batch Outputs (Silver Layer - Fibonacci Resampling)
output "fibonacci_batch_job_queue_arn" {
  description = "ARN of the Fibonacci resampling batch job queue"
  value       = aws_batch_job_queue.fibonacci_resampling.arn
}

output "fibonacci_batch_job_queue_name" {
  description = "Name of the Fibonacci resampling batch job queue"
  value       = aws_batch_job_queue.fibonacci_resampling.name
}

output "fibonacci_batch_job_definition_arn" {
  description = "ARN of the Fibonacci resampling batch job definition"
  value       = aws_batch_job_definition.fibonacci_resampling.arn
}

output "fibonacci_batch_job_definition_name" {
  description = "Name of the Fibonacci resampling batch job definition"
  value       = aws_batch_job_definition.fibonacci_resampling.name
}

# ECR Repository Output
output "fibonacci_resampler_ecr_repository_url" {
  description = "URL of the ECR repository for Fibonacci resampler"
  value       = aws_ecr_repository.fibonacci_resampler.repository_url
}

output "fibonacci_resampler_ecr_repository_name" {
  description = "Name of the ECR repository for Fibonacci resampler"
  value       = aws_ecr_repository.fibonacci_resampler.name
}

# IAM Role Outputs
output "batch_execution_role_arn" {
  description = "ARN of the batch execution role"
  value       = aws_iam_role.batch_execution_role.arn
}

output "batch_task_role_arn" {
  description = "ARN of the batch task role"
  value       = aws_iam_role.batch_task_role.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution_role.arn
}

# CloudWatch Outputs
output "batch_log_group_name" {
  description = "Name of the CloudWatch log group for batch jobs"
  value       = aws_cloudwatch_log_group.batch_jobs.name
}

output "lambda_log_group_name" {
  description = "Name of the CloudWatch log group for Lambda function"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

# Scheduling Outputs
output "daily_schedule_rule_arn" {
  description = "ARN of the EventBridge rule for daily scheduling"
  value       = aws_cloudwatch_event_rule.daily_resampling.arn
}

# Configuration Outputs
output "fibonacci_intervals" {
  description = "Fibonacci intervals being processed"
  value       = var.fibonacci_intervals
}

output "fibonacci_lookback_days" {
  description = "Number of lookback days for Fibonacci resampling"
  value       = var.fibonacci_lookback_days
}

# Cost Optimization Outputs
output "batch_compute_type" {
  description = "Batch compute type for cost optimization"
  value       = var.batch_compute_type
}

output "spot_allocation_strategy" {
  description = "Spot allocation strategy"
  value       = var.spot_allocation_strategy
}

# Security Outputs
output "batch_security_group_id" {
  description = "ID of the security group for batch jobs"
  value       = aws_security_group.batch_compute.id
}

# Environment Configuration
output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

# Integration Outputs (for triggering from other layers)
output "batch_layer_integration" {
  description = "Integration configuration for other layers"
  value = {
    job_queue_name      = aws_batch_job_queue.fibonacci_resampling.name
    job_definition_name = aws_batch_job_definition.fibonacci_resampling.name
    execution_role_arn  = aws_iam_role.batch_execution_role.arn
    task_role_arn      = aws_iam_role.batch_task_role.arn
    ecr_repository_url = aws_ecr_repository.fibonacci_resampler.repository_url
  }
}

# Performance Monitoring Outputs
output "performance_targets" {
  description = "Performance targets for Fibonacci resampling"
  value = {
    target_duration_seconds = 60  # Sub-minute target
    intervals_count        = length(var.fibonacci_intervals)
    lookback_days         = var.fibonacci_lookback_days
    expected_monthly_cost = "$5-15"  # Estimated with Fargate Spot
  }
}
