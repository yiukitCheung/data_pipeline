# Required providers
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

# ECR Repository for Fibonacci Resampler Container
resource "aws_ecr_repository" "fibonacci_resampler" {
  name                 = "${var.name_prefix}-fibonacci-resampler"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampler-ecr"
  })
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "fibonacci_resampler" {
  repository = aws_ecr_repository.fibonacci_resampler.name

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

# Batch Compute Environment (Fargate Spot)
resource "aws_batch_compute_environment" "fibonacci_resampling" {
  compute_environment_name = "${var.name_prefix}-fibonacci-resampling"
  type                    = "MANAGED"
  state                   = "ENABLED"
  service_role           = var.batch_service_role_arn

  compute_resources {
    type                = "FARGATE_SPOT"
    max_vcpus          = 256
    min_vcpus          = 0
    security_group_ids = [var.batch_security_group_id]
    subnets            = var.private_subnet_ids
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampling-compute"
  })
}

# Batch Job Queue
resource "aws_batch_job_queue" "fibonacci_resampling" {
  name                 = "${var.name_prefix}-fibonacci-resampling"
  state                = "ENABLED"
  priority             = 1
  compute_environment_order {
    compute_environment = aws_batch_compute_environment.fibonacci_resampling.arn
    order               = 1
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampling-queue"
  })
}

# Batch Job Definition
resource "aws_batch_job_definition" "fibonacci_resampler" {
  name = "${var.name_prefix}-fibonacci-resampler"
  type = "container"

  platform_capabilities = ["FARGATE"]

  container_properties = jsonencode({
    image = "${aws_ecr_repository.fibonacci_resampler.repository_url}:latest"
    
    resourceRequirements = [
      {
        type  = "VCPU"
        value = "2"
      },
      {
        type  = "MEMORY"
        value = "4096"
      }
    ]
    
    jobRoleArn = var.batch_job_role_arn
    executionRoleArn = var.batch_execution_role_arn

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      },
      {
        name  = "DB_NAME"
        value = var.database_name
      },
      {
        name  = "DB_PORT"
        value = tostring(var.database_port)
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = var.cloudwatch_log_group_name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "batch"
      }
    }

    networkConfiguration = {
      assignPublicIp = "DISABLED"
    }
  })

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-fibonacci-resampler-job"
  })
}

# EventBridge Rule for Daily Resampling
resource "aws_cloudwatch_event_rule" "daily_resampling" {
  name                = "${var.name_prefix}-daily-resampling"
  description         = "Trigger daily resampling after market close"
  schedule_expression = var.resampling_schedule_expression

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-daily-resampling-rule"
  })
}

# EventBridge Target - Use Lambda to trigger Batch job
resource "aws_cloudwatch_event_target" "daily_resampling" {
  rule      = aws_cloudwatch_event_rule.daily_resampling.name
  target_id = "BatchTarget"
  arn       = aws_lambda_function.batch_trigger.arn
  input     = jsonencode({
    "jobName"       = "${var.name_prefix}-daily-resampling-${formatdate("YYYY-MM-DD", timestamp())}",
    "jobDefinition" = aws_batch_job_definition.fibonacci_resampler.arn,
    "jobQueue"      = aws_batch_job_queue.fibonacci_resampling.arn
  })
}

# Lambda function to trigger Batch job
resource "aws_lambda_function" "batch_trigger" {
  filename         = "batch_trigger.zip"
  function_name    = "${var.name_prefix}-batch-trigger"
  role            = var.lambda_execution_role_arn
  handler         = "batch_trigger.lambda_handler"
  runtime         = "python3.11"
  timeout         = 60

  depends_on = [null_resource.batch_trigger_zip]

  environment {
    variables = {
      JOB_QUEUE = aws_batch_job_queue.fibonacci_resampling.arn
      JOB_DEFINITION = aws_batch_job_definition.fibonacci_resampler.arn
    }
  }
}

# Create a simple Lambda function to trigger Batch
resource "local_file" "batch_trigger_code" {
  filename = "batch_trigger.py"
  content = <<EOF
import json
import boto3
import os

def lambda_handler(event, context):
    batch = boto3.client('batch')
    
    job_name = event.get('jobName', 'daily-resampling-job')
    job_definition = event.get('jobDefinition')
    job_queue = event.get('jobQueue')
    
    response = batch.submit_job(
        jobName=job_name,
        jobQueue=job_queue,
        jobDefinition=job_definition
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }
EOF
}

# Create ZIP file for Lambda
resource "null_resource" "batch_trigger_zip" {
  depends_on = [local_file.batch_trigger_code]
  
  provisioner "local-exec" {
    command = "zip batch_trigger.zip batch_trigger.py"
  }
}

# CloudWatch Log Group for Batch Jobs
resource "aws_cloudwatch_log_group" "batch_jobs" {
  name              = var.cloudwatch_log_group_name
  retention_in_days = 30

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-batch-logs"
  })
}

# Outputs are defined in outputs.tf