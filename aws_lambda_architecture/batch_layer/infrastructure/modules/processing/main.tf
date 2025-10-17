# DuckDB + S3 + RDS Resampler Infrastructure
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ca-west-1"
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

# Local values
locals {
  name_prefix = "${var.environment}-batch-duckdb-resampler"
  common_tags = {
    Environment = var.environment
    Component   = "resampler"
    Technology  = "duckdb-s3-rds"
    ManagedBy   = "terraform"
  }
}

# ECR Repository for Docker images
resource "aws_ecr_repository" "resampler" {
  name                 = local.name_prefix
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "resampler" {
  name              = "/aws/batch/${local.name_prefix}"
  retention_in_days = 30

  tags = local.common_tags
}

# IAM Role for Batch Job Execution
resource "aws_iam_role" "batch_execution_role" {
  name = "${local.name_prefix}-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM Role for Batch Job (application role)
resource "aws_iam_role" "batch_job_role" {
  name = "${local.name_prefix}-job-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM Policy for Batch Execution Role
resource "aws_iam_role_policy" "batch_execution_policy" {
  name = "${local.name_prefix}-execution-policy"
  role = aws_iam_role.batch_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.resampler.arn}:*"
      }
    ]
  })
}

# IAM Policy for Batch Job Role (S3 and RDS access)
resource "aws_iam_role_policy" "batch_job_policy" {
  name = "${local.name_prefix}-job-policy"
  role = aws_iam_role.batch_job_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::dev-condvest-datalake",
          "arn:aws:s3:::dev-condvest-datalake/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.account_id}:secret:dev-rds-credentials*"
      }
    ]
  })
}

# Batch Compute Environment
resource "aws_batch_compute_environment" "resampler" {
  compute_environment_name = local.name_prefix

  compute_resources {
    type                = "FARGATE"
    max_vcpus          = 16
    min_vcpus          = 0
    desired_vcpus      = 0
    security_group_ids = [aws_security_group.batch.id]
    subnets            = var.subnet_ids

    ec2_configuration {
      image_type = "ECS_AL2"
    }
  }

  service_role = aws_iam_role.batch_service_role.arn
  state        = "ENABLED"

  depends_on = [aws_iam_role_policy_attachment.batch_service_role_policy]

  tags = local.common_tags
}

# IAM Role for Batch Service
resource "aws_iam_role" "batch_service_role" {
  name = "${local.name_prefix}-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "batch.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Attach AWS managed policy for Batch service
resource "aws_iam_role_policy_attachment" "batch_service_role_policy" {
  role       = aws_iam_role.batch_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

# Security Group for Batch
resource "aws_security_group" "batch" {
  name_prefix = local.name_prefix
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-sg"
  })
}

# Batch Job Queue
resource "aws_batch_job_queue" "resampler" {
  name                 = local.name_prefix
  state                = "ENABLED"
  priority             = 1
  compute_environments = [aws_batch_compute_environment.resampler.arn]

  tags = local.common_tags
}

# Batch Job Definition
resource "aws_batch_job_definition" "resampler" {
  name = local.name_prefix
  type = "container"

  container_properties = jsonencode({
    image = "${aws_ecr_repository.resampler.repository_url}:latest"
    vcpus = 2
    memory = 4096
    
    jobRoleArn = aws_iam_role.batch_job_role.arn
    executionRoleArn = aws_iam_role.batch_execution_role.arn
    
    environment = [
      {
        name  = "AWS_REGION"
        value = var.aws_region
      },
      {
        name  = "S3_BUCKET_NAME"
        value = "dev-condvest-datalake"
      },
      {
        name  = "RESAMPLING_INTERVALS"
        value = "3,5,8,13,21,34"
      }
    ]
    
    secrets = [
      {
        name      = "RDS_SECRET_ARN"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${var.account_id}:secret:dev-rds-credentials"
      }
    ]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.resampler.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "resampler"
      }
    }
    
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
  })

  retry_strategy {
    attempts = 3
  }

  timeout {
    attempt_duration_seconds = 3600
  }

  tags = local.common_tags
}

# Outputs
output "ecr_repository_url" {
  description = "ECR repository URL for the resampler image"
  value       = aws_ecr_repository.resampler.repository_url
}

output "batch_job_definition_arn" {
  description = "ARN of the Batch job definition"
  value       = aws_batch_job_definition.resampler.arn
}

output "batch_job_queue_arn" {
  description = "ARN of the Batch job queue"
  value       = aws_batch_job_queue.resampler.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.resampler.name
}
