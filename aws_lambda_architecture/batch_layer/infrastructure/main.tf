# ===============================================
# Batch Layer - Main Infrastructure Orchestration
# ===============================================

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }

  backend "s3" {
    bucket = "condvest-terraform-state"
    key    = "batch-layer/terraform.tfstate"
    region = "ca-west-1"
  }
}

# Configure AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Local values
locals {
  name_prefix = "${var.environment}-batch"
  common_tags = {
    Project     = "CondVest"
    Environment = var.environment
    Layer       = "Batch"
    ManagedBy   = "Terraform"
  }
}

# Data sources for existing resources
data "aws_caller_identity" "current" {}

data "aws_vpc" "main" {
  default = true
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  
  filter {
    name   = "state"
    values = ["available"]
  }
}

# ===============================================
# Shared Resources Module
# ===============================================
module "shared" {
  source = "./modules/shared"

  name_prefix   = local.name_prefix
  environment   = var.environment
  aws_region    = var.aws_region
  common_tags   = local.common_tags

  # Networking
  vpc_id         = data.aws_vpc.main.id
  vpc_cidr_block = data.aws_vpc.main.cidr_block

  # Secrets (will be created by database module)
  rds_secret_arn             = module.database.postgres_secret_arn
  polygon_api_key_secret_arn = var.polygon_api_key_secret_arn
}

# ===============================================
# Database Module
# ===============================================
module "database" {
  source = "./modules/database"

  name_prefix   = local.name_prefix
  environment   = var.environment
  common_tags   = local.common_tags

  # Networking
  vpc_id                     = data.aws_vpc.main.id
  vpc_cidr_block            = data.aws_vpc.main.cidr_block
  subnet_ids                = data.aws_subnets.private.ids
  lambda_security_group_ids = [module.shared.lambda_security_group_id]
  batch_security_group_ids  = [module.shared.batch_security_group_id]

  # Database configuration
  database_name           = var.database_name
  postgres_engine_version = var.postgres_engine_version
  db_instance_class       = var.db_instance_class
  db_allocated_storage    = var.db_allocated_storage
  db_max_allocated_storage = var.db_max_allocated_storage

  # Access control
  allow_public_access = var.allow_public_access
  publicly_accessible = var.publicly_accessible

  # Security
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
}

# ===============================================
# Processing Module
# ===============================================
module "processing" {
  source = "./modules/processing"

  name_prefix   = local.name_prefix
  environment   = var.environment
  aws_region    = var.aws_region
  common_tags   = local.common_tags

  # Networking
  subnet_ids               = data.aws_subnets.private.ids
  batch_security_group_id  = module.shared.batch_security_group_id

  # Batch configuration
  batch_max_vcpus      = var.batch_max_vcpus
  batch_job_vcpus      = var.batch_job_vcpus
  batch_job_memory     = var.batch_job_memory
  fibonacci_intervals  = var.fibonacci_intervals
  log_retention_days   = var.cloudwatch_log_retention_days

  # Database configuration
  rds_secret_arn = module.database.postgres_secret_arn
  database_name  = var.database_name
  rds_endpoint   = module.database.postgres_endpoint

  # Scheduling
  resampling_schedule_expression = var.daily_schedule_expression

  # IAM roles
  batch_service_role_arn    = module.shared.batch_service_role_arn
  batch_execution_role_arn  = module.shared.batch_execution_role_arn
  batch_job_role_arn        = module.shared.batch_job_role_arn
  eventbridge_role_arn      = module.shared.eventbridge_role_arn

  depends_on = [module.shared, module.database]
}

# ===============================================
# Fetching Module
# ===============================================
module "fetching" {
  source = "./modules/fetching"

  name_prefix   = local.name_prefix
  environment   = var.environment
  common_tags   = local.common_tags

  # Lambda configuration
  lambda_runtime       = var.lambda_runtime
  lambda_timeout       = var.lambda_timeout
  lambda_memory_size   = var.lambda_memory_size
  log_retention_days   = var.cloudwatch_log_retention_days

  # Networking
  subnet_ids               = data.aws_subnets.private.ids
  lambda_security_group_id = module.shared.lambda_security_group_id

  # Database configuration
  rds_secret_arn = module.database.postgres_secret_arn
  database_name  = var.database_name
  rds_endpoint   = module.database.postgres_endpoint

  # External APIs
  polygon_api_key_secret_arn = var.polygon_api_key_secret_arn

  # Batch processing
  batch_job_queue_name      = module.processing.batch_job_queue_name
  batch_job_definition_name = module.processing.batch_job_definition_name

  # Scheduling
  daily_schedule_expression = var.daily_schedule_expression
  meta_schedule_expression  = var.meta_schedule_expression

  # Deployment
  deployment_artifacts_path = "../fetching/deployment_packages"

  # IAM
  lambda_execution_role_arn = module.shared.lambda_execution_role_arn

  # Lambda Layers
  lambda_layer_arns = var.lambda_layer_arns

  depends_on = [module.shared, module.database, module.processing]
}
