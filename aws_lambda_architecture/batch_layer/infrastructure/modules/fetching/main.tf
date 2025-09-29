# ===============================================
# Fetching Module - Data Ingestion Lambda Functions
# ===============================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# CloudWatch Log Group for OHLCV Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.name_prefix}-daily-ohlcv-fetcher"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-lambda-logs"
  })
}

# CloudWatch Log Group for metadata fetcher
resource "aws_cloudwatch_log_group" "meta_lambda_logs" {
  name              = "/aws/lambda/${var.name_prefix}-daily-meta-fetcher"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-meta-lambda-logs"
  })
}

# Lambda Function - Daily OHLCV Fetcher
resource "aws_lambda_function" "daily_ohlcv_fetcher" {
  function_name = "${var.name_prefix}-daily-ohlcv-fetcher"
  role         = var.lambda_execution_role_arn
  
  # Deployment package
  filename         = "${var.deployment_artifacts_path}/daily_ohlcv_fetcher.zip"
  source_code_hash = filebase64sha256("${var.deployment_artifacts_path}/daily_ohlcv_fetcher.zip")
  
  # Runtime configuration
  handler     = "daily_ohlcv_fetcher.lambda_handler"
  runtime     = var.lambda_runtime
  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory_size

  # VPC Configuration
  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  # Environment variables
  environment {
    variables = {
      RDS_SECRET_ARN                      = var.rds_secret_arn
      DATABASE_NAME                       = var.database_name
      RDS_ENDPOINT                        = var.rds_endpoint
      RDS_PORT                           = "5432"
      POLYGON_API_KEY_SECRET_ARN         = var.polygon_api_key_secret_arn
      BATCH_JOB_QUEUE                    = var.batch_job_queue_name
      FIBONACCI_RESAMPLING_JOB_DEFINITION = var.batch_job_definition_name
      BATCH_SIZE                         = "50"
      LOG_LEVEL                          = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_logs]

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-ohlcv-fetcher"
  })
}

# Lambda Function - Daily Metadata Fetcher
resource "aws_lambda_function" "daily_meta_fetcher" {
  function_name = "${var.name_prefix}-daily-meta-fetcher"
  description   = "Daily metadata update for symbols (market cap, sector, industry)"
  role         = var.lambda_execution_role_arn
  
  # Deployment package
  filename         = "${var.deployment_artifacts_path}/daily_meta_fetcher.zip"
  source_code_hash = filebase64sha256("${var.deployment_artifacts_path}/daily_meta_fetcher.zip")
  
  # Runtime configuration
  handler     = "daily_meta_fetcher.lambda_handler"
  runtime     = var.lambda_runtime
  timeout     = 900  # 15 minutes for metadata (longer due to rate limiting)
  memory_size = var.lambda_memory_size

  # VPC Configuration
  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  # Environment variables
  environment {
    variables = {
      RDS_SECRET_ARN             = var.rds_secret_arn
      DATABASE_NAME              = var.database_name
      RDS_ENDPOINT               = var.rds_endpoint
      RDS_PORT                   = "5432"
      POLYGON_API_KEY_SECRET_ARN = var.polygon_api_key_secret_arn
      BATCH_SIZE                 = "20"  # Smaller batches for metadata
      LOG_LEVEL                  = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.meta_lambda_logs]

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-meta-fetcher"
  })
}

# EventBridge Rule for Daily OHLCV Scheduling
resource "aws_cloudwatch_event_rule" "daily_ohlcv_fetch" {
  name                = "${var.name_prefix}-daily-ohlcv-fetch"
  description         = "Trigger daily OHLCV data fetching after market close"
  schedule_expression = var.daily_schedule_expression

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-ohlcv-fetch-rule"
  })
}

# EventBridge Rule for Daily Metadata Update
resource "aws_cloudwatch_event_rule" "daily_meta_fetch" {
  name                = "${var.name_prefix}-daily-meta-fetch"
  description         = "Trigger daily metadata update 30 minutes after OHLCV fetch"
  schedule_expression = var.meta_schedule_expression

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-meta-fetch-rule"
  })
}

# EventBridge Targets
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_ohlcv_fetch.name
  target_id = "DailyOHLCVFetchTarget"
  arn       = aws_lambda_function.daily_ohlcv_fetcher.arn
}

resource "aws_cloudwatch_event_target" "meta_lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_meta_fetch.name
  target_id = "DailyMetaFetchTarget"
  arn       = aws_lambda_function.daily_meta_fetcher.arn
}

# Lambda permissions for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_ohlcv_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ohlcv_fetch.arn
}

resource "aws_lambda_permission" "allow_eventbridge_meta" {
  statement_id  = "AllowExecutionFromEventBridgeMeta"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_meta_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_meta_fetch.arn
}
