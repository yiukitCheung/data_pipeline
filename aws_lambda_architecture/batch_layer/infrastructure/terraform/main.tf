# Terraform configuration for Batch Layer
# Purpose: Cost-efficient daily data processing and Fibonacci resampling
# Architecture: Lambda (Bronze) + AWS Batch (Silver/Fibonacci)

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "condvest-terraform-state"
    key    = "batch-layer/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "condvest-batch-layer"
      ManagedBy   = "terraform"
      Layer       = "batch"
    }
  }
}

# Data sources for existing infrastructure
data "aws_vpc" "main" {
  tags = {
    Name = "${var.environment}-condvest-vpc"
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  
  tags = {
    Type = "private"
  }
}

data "aws_security_group" "aurora" {
  name = "${var.environment}-aurora-security-group"
}

# ECR Repository for Fibonacci Resampler
resource "aws_ecr_repository" "fibonacci_resampler" {
  name                 = "${var.environment}-fibonacci-resampler"
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

  tags = {
    Name = "${var.environment}-fibonacci-resampler"
  }
}
