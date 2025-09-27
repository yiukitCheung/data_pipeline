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
    region = "ca-west-1"
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
  default = true  # Use the default VPC
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  
  # Use all subnets in the default VPC (they're all public but that's fine for this setup)
  filter {
    name   = "state"
    values = ["available"]
  }
}

# Aurora security group reference removed - now using RDS TimescaleDB

# Local values for consistent naming and configuration
locals {
  name_prefix = "${var.environment}-condvest"
  vpc_id      = data.aws_vpc.main.id
  subnet_ids  = data.aws_subnets.private.ids
  
  common_tags = {
    Environment = var.environment
    Project     = "condvest-batch-layer"
    ManagedBy   = "terraform"
    Layer       = "batch"
  }
}
