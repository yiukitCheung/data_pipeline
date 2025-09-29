# Lambda Function for Daily OHLCV Fetching
# Purpose: Bronze layer - fetch daily stock data from Polygon API

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${local.name_prefix}-daily-ohlcv-fetcher"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lambda-logs"
  })
}

# Security Group for Lambda (to access RDS)
resource "aws_security_group" "batch_lambda" {
  name_prefix = "${local.name_prefix}-lambda-"
  vpc_id      = local.vpc_id
  description = "Security group for Lambda function to access RDS"

  # Outbound access to RDS
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.main.cidr_block]  # ← Use VPC CIDR instead
    description = "PostgreSQL access to TimescaleDB"
  }
  
  # Outbound internet access for API calls
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS for API calls"
  }

  # Outbound internet access for package downloads
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP for package downloads"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lambda-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Lambda Function
resource "aws_lambda_function" "daily_ohlcv_fetcher" {
  function_name = "${local.name_prefix}-daily-ohlcv-fetcher"
  role         = aws_iam_role.lambda_execution_role.arn
  
  # Deployment package (you'll need to create this)
  filename         = "daily_ohlcv_fetcher.zip"
  source_code_hash = filebase64sha256("daily_ohlcv_fetcher.zip")
  
  # Runtime configuration
  handler = "daily_ohlcv_fetcher.lambda_handler"
  runtime = var.lambda_runtime
  timeout = var.lambda_timeout
  memory_size = var.lambda_memory_size

  # VPC Configuration
  vpc_config {
    subnet_ids         = local.subnet_ids
    security_group_ids = [aws_security_group.batch_lambda.id]
  }

  # Environment variables
  environment {
    variables = {
      RDS_SECRET_ARN                      = aws_secretsmanager_secret.postgres_credentials.arn
      DATABASE_NAME                       = var.database_name
      RDS_ENDPOINT                        = aws_db_instance.postgres.address
      RDS_PORT                           = "5432"
      POLYGON_API_KEY_SECRET_ARN         = var.polygon_api_key_secret_arn
      BATCH_JOB_QUEUE                    = aws_batch_job_queue.fibonacci_resampling.name
      FIBONACCI_RESAMPLING_JOB_DEFINITION = aws_batch_job_definition.fibonacci_resampling.name
      BATCH_SIZE                         = "50"
      LOG_LEVEL                          = "INFO"
    }
  }

  # Depends on CloudWatch log group
  depends_on = [aws_cloudwatch_log_group.lambda_logs]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-ohlcv-fetcher"
  })
}

# EventBridge Rule for Daily Scheduling
resource "aws_cloudwatch_event_rule" "daily_ohlcv_fetch" {
  name                = "${local.name_prefix}-daily-ohlcv-fetch"
  description         = "Trigger daily OHLCV data fetching after market close"
  schedule_expression = var.daily_schedule_expression

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-ohlcv-fetch-rule"
  })
}

# EventBridge Target (Lambda)
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_ohlcv_fetch.name
  target_id = "DailyOHLCVFetchTarget"
  arn       = aws_lambda_function.daily_ohlcv_fetcher.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_ohlcv_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ohlcv_fetch.arn
}

# ===============================================
# Daily Metadata Fetcher Lambda Function
# ===============================================

# CloudWatch Log Group for metadata fetcher
resource "aws_cloudwatch_log_group" "meta_lambda_logs" {
  name              = "/aws/lambda/${local.name_prefix}-daily-meta-fetcher"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-meta-lambda-logs"
  })
}

# Daily Metadata Fetcher Lambda Function
resource "aws_lambda_function" "daily_meta_fetcher" {
  function_name = "${local.name_prefix}-daily-meta-fetcher"
  description   = "Daily metadata update for symbols (market cap, sector, industry)"
  role         = aws_iam_role.lambda_execution_role.arn
  
  # Deployment package (you'll need to create this)
  filename         = "daily_meta_fetcher.zip"
  source_code_hash = filebase64sha256("daily_meta_fetcher.zip")
  
  # Runtime configuration
  handler = "daily_meta_fetcher.lambda_handler"
  runtime = var.lambda_runtime
  timeout = 900  # 15 minutes for metadata (longer due to rate limiting)
  memory_size = var.lambda_memory_size

  # VPC Configuration
  vpc_config {
    subnet_ids         = local.subnet_ids
    security_group_ids = [aws_security_group.batch_lambda.id]
  }

  # Environment variables
  environment {
    variables = {
      RDS_SECRET_ARN             = aws_secretsmanager_secret.postgres_credentials.arn
      DATABASE_NAME              = var.database_name
      RDS_ENDPOINT               = aws_db_instance.timescale.address
      RDS_PORT                   = "5432"
      POLYGON_API_KEY_SECRET_ARN = var.polygon_api_key_secret_arn
      BATCH_SIZE                 = "20"  # Smaller batches for metadata to respect rate limits
      LOG_LEVEL                  = "INFO"
    }
  }

  # Depends on CloudWatch log group
  depends_on = [aws_cloudwatch_log_group.meta_lambda_logs]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-meta-fetcher"
  })
}

# EventBridge Rule for Daily Metadata Update (30 minutes after OHLCV)
resource "aws_cloudwatch_event_rule" "daily_meta_fetch" {
  name                = "${local.name_prefix}-daily-meta-fetch"
  description         = "Trigger daily metadata update 30 minutes after OHLCV fetch"
schedule_expression = "cron(35 21 * * ? *)"  # 4:35 PM EST weekdays (9:35 PM UTC)
  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-meta-fetch-rule"
  })
}

# EventBridge Target (Lambda)
resource "aws_cloudwatch_event_target" "meta_lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_meta_fetch.name
  target_id = "DailyMetaFetchTarget"
  arn       = aws_lambda_function.daily_meta_fetcher.arn
}

# Lambda permission for EventBridge (metadata)
resource "aws_lambda_permission" "allow_eventbridge_meta" {
  statement_id  = "AllowExecutionFromEventBridgeMeta"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_meta_fetcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_meta_fetch.arn
}
