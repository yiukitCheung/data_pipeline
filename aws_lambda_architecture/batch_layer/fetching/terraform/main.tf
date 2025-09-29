# ===============================================
# Fetching Component - Testing Infrastructure
# ===============================================

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "condvest-terraform-state"
    key    = "batch-layer/components/fetching/terraform.tfstate"
    region = "ca-west-1"
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = "${var.environment}-fetching-test"
  common_tags = {
    Project     = "CondVest"
    Environment = var.environment
    Component   = "Fetching"
    Purpose     = "Testing"
    ManagedBy   = "Terraform"
  }
}

# Data sources
data "aws_vpc" "main" {
  default = true
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
}

# Use the fetching module for testing
module "fetching_test" {
  source = "../../infrastructure/modules/fetching"

  name_prefix   = local.name_prefix
  environment   = var.environment
  common_tags   = local.common_tags

  # Mock/test configuration
  lambda_runtime       = "python3.11"
  lambda_timeout       = 60  # Shorter for testing
  lambda_memory_size   = 128 # Smaller for testing
  log_retention_days   = 3   # Shorter retention for testing

  # Networking
  subnet_ids               = data.aws_subnets.private.ids
  lambda_security_group_id = aws_security_group.test_lambda.id

  # Mock database configuration
  rds_secret_arn = aws_secretsmanager_secret.test_credentials.arn
  database_name  = "test_condvest"
  rds_endpoint   = "test-endpoint.amazonaws.com"

  # External APIs
  polygon_api_key_secret_arn = var.polygon_api_key_secret_arn

  # Mock batch processing
  batch_job_queue_name      = "test-queue"
  batch_job_definition_name = "test-job-definition"

  # Disabled scheduling for testing
  daily_schedule_expression = "cron(0 12 * * ? *)"  # Once daily at noon
  meta_schedule_expression  = "cron(30 12 * * ? *)" # 30 minutes later

  # Test deployment path
  deployment_artifacts_path = "../deployment_packages"

  # IAM
  lambda_execution_role_arn = aws_iam_role.test_lambda_role.arn
}

# Test security group
resource "aws_security_group" "test_lambda" {
  name_prefix = "${local.name_prefix}-lambda-"
  vpc_id      = data.aws_vpc.main.id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# Test IAM role
resource "aws_iam_role" "test_lambda_role" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "test_lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.test_lambda_role.name
}

# Test secret
resource "aws_secretsmanager_secret" "test_credentials" {
  name = "${local.name_prefix}-test-credentials"
  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "test_credentials" {
  secret_id = aws_secretsmanager_secret.test_credentials.id
  secret_string = jsonencode({
    username = "test_user"
    password = "test_password"
    host     = "test-host"
    port     = 5432
    dbname   = "test_db"
  })
}
