# Variables for Speed Layer Terraform Configuration

# Environment Configuration
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

# Networking Configuration
variable "vpc_id" {
  description = "VPC ID to deploy resources (empty for default VPC)"
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnet IDs for ECS tasks (null for default subnets)"
  type        = list(string)
  default     = null
}

# ECS Configuration
variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
  default     = ""
}

variable "websocket_service_cpu" {
  description = "CPU units for WebSocket service (256, 512, 1024, etc.)"
  type        = number
  default     = 512
  
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.websocket_service_cpu)
    error_message = "CPU must be one of: 256, 512, 1024, 2048, 4096."
  }
}

variable "websocket_service_memory" {
  description = "Memory (MB) for WebSocket service"
  type        = number
  default     = 1024
  
  validation {
    condition     = var.websocket_service_memory >= 512 && var.websocket_service_memory <= 30720
    error_message = "Memory must be between 512 and 30720 MB."
  }
}

variable "websocket_desired_count" {
  description = "Desired number of WebSocket service instances"
  type        = number
  default     = 1
  
  validation {
    condition     = var.websocket_desired_count >= 1 && var.websocket_desired_count <= 10
    error_message = "Desired count must be between 1 and 10."
  }
}

# Kinesis Configuration
variable "kinesis_shard_count" {
  description = "Number of shards for main Kinesis streams"
  type        = number
  default     = 2
  
  validation {
    condition     = var.kinesis_shard_count >= 1 && var.kinesis_shard_count <= 10
    error_message = "Kinesis shard count must be between 1 and 10."
  }
}

variable "kinesis_retention_hours" {
  description = "Kinesis stream retention period in hours"
  type        = number
  default     = 24
  
  validation {
    condition     = var.kinesis_retention_hours >= 24 && var.kinesis_retention_hours <= 8760
    error_message = "Retention period must be between 24 and 8760 hours."
  }
}

# ElastiCache Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 1
  
  validation {
    condition     = var.redis_num_cache_nodes >= 1 && var.redis_num_cache_nodes <= 20
    error_message = "Number of cache nodes must be between 1 and 20."
  }
}

variable "redis_port" {
  description = "Redis port number"
  type        = number
  default     = 6379
}

# External API Configuration
variable "polygon_api_key" {
  description = "Polygon.io API key for market data"
  type        = string
  sensitive   = true
}

# Monitoring Configuration
variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 14
  
  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653
    ], var.log_retention_days)
    error_message = "Log retention days must be a valid CloudWatch retention period."
  }
}

# Security Configuration
variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access health check endpoints"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # Restrict this in production
}

# Scaling Configuration
variable "enable_auto_scaling" {
  description = "Enable auto scaling for ECS service"
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum capacity for auto scaling"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum capacity for auto scaling"
  type        = number
  default     = 5
}

variable "target_cpu_utilization" {
  description = "Target CPU utilization for auto scaling"
  type        = number
  default     = 70
  
  validation {
    condition     = var.target_cpu_utilization >= 10 && var.target_cpu_utilization <= 90
    error_message = "Target CPU utilization must be between 10 and 90."
  }
}

# ECR Repository Configuration
variable "ecr_repository_name" {
  description = "ECR repository name for WebSocket service"
  type        = string
  default     = "condvest-speed-websocket"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# Feature Flags
variable "enable_kinesis_analytics" {
  description = "Enable Kinesis Analytics applications"
  type        = bool
  default     = true
}

variable "enable_signal_detection" {
  description = "Enable signal detection Flink applications"
  type        = bool
  default     = false  # Start with false for MVP
}

# Cost Optimization
variable "enable_spot_instances" {
  description = "Use Spot instances for ECS tasks (cost optimization)"
  type        = bool
  default     = false  # Set to true for dev environment
}
