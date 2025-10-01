# ===============================================
# Database Module - Lambda Functions
# ===============================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Database Initialization Lambda Function
resource "aws_lambda_function" "db_init" {
  filename         = "db_init.zip"
  function_name    = "${var.name_prefix}-db-init"
  role            = var.lambda_execution_role_arn
  handler         = "db_init.lambda_handler"
  runtime         = "python3.11"
  timeout         = 300  # 5 minutes for database initialization

  depends_on = [null_resource.db_init_zip]

  environment {
    variables = {
      DB_HOST     = var.database_host
      DB_PORT     = tostring(var.database_port)
      DB_NAME     = var.database_name
      DB_USER     = var.database_user
      DB_PASSWORD = var.database_password
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-db-init"
  })
}

# Create ZIP file for Lambda
resource "null_resource" "db_init_zip" {
  provisioner "local-exec" {
    command = "cd ${path.module}/lambda_functions && zip -r ../db_init.zip ."
  }
}

# CloudWatch Log Group for DB Init
resource "aws_cloudwatch_log_group" "db_init" {
  name              = "/aws/lambda/${var.name_prefix}-db-init"
  retention_in_days = 14

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-db-init-logs"
  })
}

# EventBridge Rule to trigger DB init after database creation
resource "aws_cloudwatch_event_rule" "db_init_trigger" {
  name                = "${var.name_prefix}-db-init-trigger"
  description         = "Trigger database initialization after RDS is ready"
  schedule_expression = "rate(2 minutes)"  # Run every 2 minutes until successful
  is_enabled          = false  # Disabled by default, enable manually

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-db-init-trigger"
  })
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "db_init_trigger" {
  rule      = aws_cloudwatch_event_rule.db_init_trigger.name
  target_id = "DBInitTarget"
  arn       = aws_lambda_function.db_init.arn
}

# Manual trigger for database initialization
resource "aws_lambda_invocation" "db_init_manual" {
  function_name = aws_lambda_function.db_init.function_name
  input = jsonencode({
    "manual_trigger" = true
  })

  depends_on = [aws_lambda_function.db_init]
}
