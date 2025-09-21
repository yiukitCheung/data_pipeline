# Terraform Configuration for Speed Layer Infrastructure
# Purpose: Real-time data ingestion, processing, and signal generation

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Backend configuration for state management
  backend "s3" {
    # These values should be provided via backend config file or CLI
    # bucket = "condvest-terraform-state"
    # key    = "speed-layer/terraform.tfstate"
    # region = "us-east-1"
    # encrypt = true
    # dynamodb_table = "terraform-locks"
  }
}

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "condvest"
      Component   = "speed-layer"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Data sources for existing resources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# VPC and networking (if not provided)
data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

data "aws_vpc" "selected" {
  count = var.vpc_id != "" ? 1 : 0
  id    = var.vpc_id
}

data "aws_subnets" "default" {
  count = var.subnet_ids == null ? 1 : 0
  
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
  
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

locals {
  # Determine VPC and subnets to use
  vpc_id = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = var.subnet_ids != null ? var.subnet_ids : data.aws_subnets.default[0].ids
  
  # Common tags
  common_tags = {
    Project     = "condvest"
    Component   = "speed-layer"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  
  # Resource naming
  name_prefix = "condvest-speed-${var.environment}"
}
