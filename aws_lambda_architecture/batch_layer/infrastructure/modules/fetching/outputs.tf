# ===============================================
# Fetching Module Outputs
# ===============================================

output "daily_ohlcv_fetcher_function_arn" {
  description = "ARN of the daily OHLCV fetcher Lambda function"
  value       = aws_lambda_function.daily_ohlcv_fetcher.arn
}

output "daily_ohlcv_fetcher_function_name" {
  description = "Name of the daily OHLCV fetcher Lambda function"
  value       = aws_lambda_function.daily_ohlcv_fetcher.function_name
}

output "daily_meta_fetcher_function_arn" {
  description = "ARN of the daily metadata fetcher Lambda function"
  value       = aws_lambda_function.daily_meta_fetcher.arn
}

output "daily_meta_fetcher_function_name" {
  description = "Name of the daily metadata fetcher Lambda function"
  value       = aws_lambda_function.daily_meta_fetcher.function_name
}

output "daily_ohlcv_schedule_rule_arn" {
  description = "ARN of the daily OHLCV fetch EventBridge rule"
  value       = aws_cloudwatch_event_rule.daily_ohlcv_fetch.arn
}

output "daily_meta_schedule_rule_arn" {
  description = "ARN of the daily metadata fetch EventBridge rule"
  value       = aws_cloudwatch_event_rule.daily_meta_fetch.arn
}

output "ohlcv_lambda_log_group_name" {
  description = "CloudWatch log group name for OHLCV Lambda"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "meta_lambda_log_group_name" {
  description = "CloudWatch log group name for metadata Lambda"
  value       = aws_cloudwatch_log_group.meta_lambda_logs.name
}
