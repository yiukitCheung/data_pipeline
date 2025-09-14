# ===============================================
# AWS Lambda Architecture Infrastructure
# ===============================================

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
  
  default_tags {
    tags = {
      Project     = "condvest-data-pipeline"
      Environment = var.environment
      Architecture = "lambda"
      ManagedBy   = "terraform"
    }
  }
}

# ===============================================
# Data Sources
# ===============================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ===============================================
# Locals
# ===============================================

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  
  common_tags = {
    Project     = "condvest-data-pipeline"
    Environment = var.environment
    Architecture = "lambda"
  }
}
