# ===============================================
# Shared Module Outputs
# ===============================================

# IAM Role ARNs
output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution_role.arn
}

output "batch_service_role_arn" {
  description = "ARN of the Batch service role"
  value       = aws_iam_role.batch_service_role.arn
}

output "batch_execution_role_arn" {
  description = "ARN of the Batch execution role"
  value       = aws_iam_role.batch_execution_role.arn
}

output "batch_job_role_arn" {
  description = "ARN of the Batch job role"
  value       = aws_iam_role.batch_job_role.arn
}

output "eventbridge_role_arn" {
  description = "ARN of the EventBridge role for Batch"
  value       = aws_iam_role.eventbridge_role.arn
}

# Security Group IDs
output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  value       = aws_security_group.lambda.id
}

output "batch_security_group_id" {
  description = "Security group ID for Batch compute environment"
  value       = aws_security_group.batch_compute.id
}
