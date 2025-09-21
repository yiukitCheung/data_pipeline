# Terraform Outputs for Speed Layer Infrastructure
# Purpose: Export key resource information for other modules and external use

# Kinesis Streams
output "kinesis_streams" {
  description = "Kinesis stream details for data flow"
  value = {
    raw = {
      name = aws_kinesis_stream.market_data_raw.name
      arn  = aws_kinesis_stream.market_data_raw.arn
      id   = aws_kinesis_stream.market_data_raw.id
    }
    ohlcv_1min = {
      name = aws_kinesis_stream.market_data_1min.name
      arn  = aws_kinesis_stream.market_data_1min.arn
      id   = aws_kinesis_stream.market_data_1min.id
    }
    ohlcv_5min = {
      name = aws_kinesis_stream.market_data_5min.name
      arn  = aws_kinesis_stream.market_data_5min.arn
      id   = aws_kinesis_stream.market_data_5min.id
    }
    ohlcv_15min = {
      name = aws_kinesis_stream.market_data_15min.name
      arn  = aws_kinesis_stream.market_data_15min.arn
      id   = aws_kinesis_stream.market_data_15min.id
    }
    ohlcv_1hour = {
      name = aws_kinesis_stream.market_data_1hour.name
      arn  = aws_kinesis_stream.market_data_1hour.arn
      id   = aws_kinesis_stream.market_data_1hour.id
    }
    ohlcv_2hour = {
      name = aws_kinesis_stream.market_data_2hour.name
      arn  = aws_kinesis_stream.market_data_2hour.arn
      id   = aws_kinesis_stream.market_data_2hour.id
    }
    ohlcv_4hour = {
      name = aws_kinesis_stream.market_data_4hour.name
      arn  = aws_kinesis_stream.market_data_4hour.arn
      id   = aws_kinesis_stream.market_data_4hour.id
    }
    trading_signals = {
      name = aws_kinesis_stream.trading_signals.name
      arn  = aws_kinesis_stream.trading_signals.arn
      id   = aws_kinesis_stream.trading_signals.id
    }
  }
}

# ECS Infrastructure
output "ecs_cluster" {
  description = "ECS cluster information"
  value = {
    id   = aws_ecs_cluster.speed_layer.id
    name = aws_ecs_cluster.speed_layer.name
    arn  = aws_ecs_cluster.speed_layer.arn
  }
}

output "websocket_service" {
  description = "WebSocket service details"
  value = {
    service_name     = aws_ecs_service.websocket_service.name
    service_arn      = aws_ecs_service.websocket_service.id
    task_definition  = aws_ecs_task_definition.websocket_service.arn
    health_check_url = "http://${aws_lb.websocket_service.dns_name}/health"
    alb_dns_name     = aws_lb.websocket_service.dns_name
    alb_zone_id      = aws_lb.websocket_service.zone_id
  }
}

output "ecr_repository" {
  description = "ECR repository for WebSocket service"
  value = {
    url  = aws_ecr_repository.websocket_service.repository_url
    name = aws_ecr_repository.websocket_service.name
    arn  = aws_ecr_repository.websocket_service.arn
  }
}

# ElastiCache Redis
output "redis_cluster" {
  description = "ElastiCache Redis cluster details"
  value = {
    id                     = aws_elasticache_replication_group.redis.id
    primary_endpoint       = aws_elasticache_replication_group.redis.primary_endpoint_address
    reader_endpoint_address = aws_elasticache_replication_group.redis.reader_endpoint_address
    port                   = aws_elasticache_replication_group.redis.port
    configuration_endpoint = aws_elasticache_replication_group.redis.configuration_endpoint_address
  }
  sensitive = true  # Redis endpoints may be sensitive
}

# IAM Roles
output "iam_roles" {
  description = "IAM roles for speed layer components"
  value = {
    ecs_execution_role = {
      name = aws_iam_role.ecs_execution_role.name
      arn  = aws_iam_role.ecs_execution_role.arn
    }
    ecs_task_role = {
      name = aws_iam_role.ecs_task_role.name
      arn  = aws_iam_role.ecs_task_role.arn
    }
    kinesis_analytics_role = {
      name = aws_iam_role.kinesis_analytics_role.name
      arn  = aws_iam_role.kinesis_analytics_role.arn
    }
    cloudwatch_events_role = {
      name = aws_iam_role.cloudwatch_events_role.name
      arn  = aws_iam_role.cloudwatch_events_role.arn
    }
  }
}

# Security Groups
output "security_groups" {
  description = "Security groups for speed layer components"
  value = {
    websocket_service = {
      id   = aws_security_group.websocket_service.id
      name = aws_security_group.websocket_service.name
    }
    websocket_alb = {
      id   = aws_security_group.websocket_alb.id
      name = aws_security_group.websocket_alb.name
    }
    redis = {
      id   = aws_security_group.redis.id
      name = aws_security_group.redis.name
    }
  }
}

# CloudWatch Resources
output "cloudwatch_log_groups" {
  description = "CloudWatch log groups for monitoring"
  value = {
    websocket_service     = aws_cloudwatch_log_group.websocket_service.name
    kinesis_analytics     = aws_cloudwatch_log_group.kinesis_analytics_logs.name
    kinesis_streams       = aws_cloudwatch_log_group.kinesis_streams_logs.name
    redis_slow_log        = aws_cloudwatch_log_group.redis_slow_log.name
  }
}

# KMS Key
output "kms_key" {
  description = "KMS key for encryption"
  value = {
    id   = aws_kms_key.kinesis_key.id
    arn  = aws_kms_key.kinesis_key.arn
    alias = aws_kms_alias.kinesis_key_alias.name
  }
}

# Network Configuration
output "network_config" {
  description = "Network configuration used by speed layer"
  value = {
    vpc_id     = local.vpc_id
    subnet_ids = local.subnet_ids
  }
}

# Resource Naming
output "resource_naming" {
  description = "Resource naming convention for consistency"
  value = {
    name_prefix = local.name_prefix
    environment = var.environment
    aws_region  = var.aws_region
  }
}

# Auto Scaling (if enabled)
output "auto_scaling" {
  description = "Auto scaling configuration"
  value = var.enable_auto_scaling ? {
    target_arn          = aws_appautoscaling_target.websocket_service[0].arn
    policy_arn          = aws_appautoscaling_policy.websocket_service_cpu[0].arn
    min_capacity        = var.min_capacity
    max_capacity        = var.max_capacity
    target_cpu_utilization = var.target_cpu_utilization
  } : null
}

# Environment Variables for Applications
output "environment_variables" {
  description = "Environment variables for speed layer applications"
  value = {
    KINESIS_STREAM_RAW      = aws_kinesis_stream.market_data_raw.name
    KINESIS_STREAM_1MIN     = aws_kinesis_stream.market_data_1min.name
    KINESIS_STREAM_5MIN     = aws_kinesis_stream.market_data_5min.name
    KINESIS_STREAM_15MIN    = aws_kinesis_stream.market_data_15min.name
    KINESIS_STREAM_1HOUR    = aws_kinesis_stream.market_data_1hour.name
    KINESIS_STREAM_2HOUR    = aws_kinesis_stream.market_data_2hour.name
    KINESIS_STREAM_4HOUR    = aws_kinesis_stream.market_data_4hour.name
    KINESIS_STREAM_SIGNALS  = aws_kinesis_stream.trading_signals.name
    REDIS_ENDPOINT          = aws_elasticache_replication_group.redis.primary_endpoint_address
    REDIS_PORT              = aws_elasticache_replication_group.redis.port
    AWS_REGION              = var.aws_region
    ENVIRONMENT             = var.environment
  }
  sensitive = true  # Contains endpoint information
}
