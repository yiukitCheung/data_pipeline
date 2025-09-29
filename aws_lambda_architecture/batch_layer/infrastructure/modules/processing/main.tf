# ===============================================
# Processing Module - AWS Batch for Data Resampling
# ===============================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ECR Repository for Batch Job
resource "aws_ecr_repository" "fibonacci_resampler" {
  name                 = "${var.name_prefix}-fibonacci-resampler"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle_policy {
    policy = jsonencode({
      rules = [
        {
          rulePriority = 1
          description  = "Keep last 10 images"
          selection = {
            tagStatus     = "tagged"
            tagPrefixList = ["v"]
            countType     = "imageCountMoreThan"
            countNumber   = 10
          }
          action = {
            type = "expire"
          }
        }
      ]
    })
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampler-ecr"
  })
}

# Batch Compute Environment (Fargate Spot)
resource "aws_batch_compute_environment" "fibonacci_resampling" {
  compute_environment_name = "${var.name_prefix}-fibonacci-resampling"
  type                    = "MANAGED"
  state                   = "ENABLED"
  service_role           = var.batch_service_role_arn

  compute_resources {
    type                = "FARGATE_SPOT"
    max_vcpus          = var.batch_max_vcpus
    subnets            = var.subnet_ids
    security_group_ids = [var.batch_security_group_id]
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampling-compute"
  })
}

# Batch Job Queue
resource "aws_batch_job_queue" "fibonacci_resampling" {
  name                 = "${var.name_prefix}-fibonacci-resampling-queue"
  state               = "ENABLED"
  priority            = 1
  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.fibonacci_resampling.arn
  }
  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampling-queue"
  })
}

# Batch Job Definition
resource "aws_batch_job_definition" "fibonacci_resampling" {
  name = "${var.name_prefix}-fibonacci-resampling"
  type = "container"
  
  platform_capabilities = ["FARGATE"]

  container_properties = jsonencode({
    image = "${aws_ecr_repository.fibonacci_resampler.repository_url}:latest"
    
    # Fargate resource requirements
    resourceRequirements = [
      {
        type  = "VCPU"
        value = var.batch_job_vcpus
      },
      {
        type  = "MEMORY"
        value = var.batch_job_memory
      }
    ]

    # Execution role for Fargate
    executionRoleArn = var.batch_execution_role_arn
    jobRoleArn      = var.batch_job_role_arn

    # Environment variables
    environment = [
      {
        name  = "RDS_SECRET_ARN"
        value = var.rds_secret_arn
      },
      {
        name  = "DATABASE_NAME"
        value = var.database_name
      },
      {
        name  = "RDS_ENDPOINT"
        value = var.rds_endpoint
      },
      {
        name  = "FIBONACCI_INTERVALS"
        value = var.fibonacci_intervals
      },
      {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
    ]

    # CloudWatch logs
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch_logs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "fibonacci-resampling"
      }
    }
  })

  retry_strategy {
    attempts = 3
  }

  timeout {
    attempt_duration_seconds = 3600  # 1 hour timeout
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampling-job"
  })
}

# CloudWatch Log Group for Batch
resource "aws_cloudwatch_log_group" "batch_logs" {
  name              = "/aws/batch/${var.name_prefix}-fibonacci-resampling"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-batch-logs"
  })
}

# EventBridge Rule for Daily Resampling (triggered after OHLCV fetch)
resource "aws_cloudwatch_event_rule" "daily_resampling" {
  name                = "${var.name_prefix}-daily-resampling"
  description         = "Trigger Fibonacci resampling after daily OHLCV fetch"
  schedule_expression = var.resampling_schedule_expression

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-resampling-rule"
  })
}

# EventBridge Target (Batch Job)
resource "aws_cloudwatch_event_target" "batch_resampling" {
  rule      = aws_cloudwatch_event_rule.daily_resampling.name
  target_id = "DailyResamplingTarget"
  arn       = aws_batch_job_queue.fibonacci_resampling.arn
  role_arn  = var.eventbridge_role_arn

  batch_target {
    job_definition = aws_batch_job_definition.fibonacci_resampling.arn
    job_name       = "${var.name_prefix}-daily-fibonacci-resampling"
  }
}
