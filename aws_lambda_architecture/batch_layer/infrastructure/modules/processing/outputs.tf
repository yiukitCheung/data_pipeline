# ===============================================
# Processing Module Outputs
# ===============================================

output "ecr_repository_url" {
  description = "URL of the ECR repository for fibonacci resampler"
  value       = aws_ecr_repository.fibonacci_resampler.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.fibonacci_resampler.arn
}

output "batch_compute_environment_arn" {
  description = "ARN of the Batch compute environment"
  value       = aws_batch_compute_environment.fibonacci_resampling.arn
}

output "batch_job_queue_name" {
  description = "Name of the Batch job queue"
  value       = aws_batch_job_queue.fibonacci_resampling.name
}

output "batch_job_queue_arn" {
  description = "ARN of the Batch job queue"
  value       = aws_batch_job_queue.fibonacci_resampling.arn
}

output "batch_job_definition_name" {
  description = "Name of the Batch job definition"
  value       = aws_batch_job_definition.fibonacci_resampling.name
}

output "batch_job_definition_arn" {
  description = "ARN of the Batch job definition"
  value       = aws_batch_job_definition.fibonacci_resampling.arn
}

output "daily_resampling_rule_arn" {
  description = "ARN of the daily resampling EventBridge rule"
  value       = aws_cloudwatch_event_rule.daily_resampling.arn
}

output "batch_log_group_name" {
  description = "CloudWatch log group name for Batch jobs"
  value       = aws_cloudwatch_log_group.batch_logs.name
}
