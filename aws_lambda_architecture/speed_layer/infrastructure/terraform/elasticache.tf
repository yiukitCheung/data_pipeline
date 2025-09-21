# ElastiCache Redis Configuration for Signal Caching
# Purpose: Cache trading signals with TTL for fast API access

# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.name_prefix}-redis-subnet-group"
  subnet_ids = local.subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-subnet-group"
  })
}

# Security Group for ElastiCache Redis
resource "aws_security_group" "redis" {
  name_prefix = "${local.name_prefix}-redis-"
  vpc_id      = local.vpc_id
  description = "Security group for ElastiCache Redis cluster"

  # Redis port access from ECS tasks and other services
  ingress {
    description     = "Redis access from ECS tasks"
    from_port       = var.redis_port
    to_port         = var.redis_port
    protocol        = "tcp"
    security_groups = [aws_security_group.websocket_service.id]
  }

  # Future: Allow access from serving layer (API Gateway Lambda functions)
  ingress {
    description = "Redis access from VPC"
    from_port   = var.redis_port
    to_port     = var.redis_port
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default[0].cidr_block]
  }

  # No outbound rules needed for Redis
  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ElastiCache Parameter Group for Redis optimization
resource "aws_elasticache_parameter_group" "redis" {
  family = "redis7.x"
  name   = "${local.name_prefix}-redis-params"
  
  description = "Custom parameter group for speed layer Redis"

  # Optimize for signal caching workload
  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"  # Evict least recently used keys when memory full
  }

  parameter {
    name  = "timeout"
    value = "300"  # 5-minute idle connection timeout
  }

  parameter {
    name  = "tcp-keepalive"
    value = "300"  # Keep-alive for better connection management
  }

  # Enable keyspace notifications for pub/sub
  parameter {
    name  = "notify-keyspace-events"
    value = "Ex"  # Notify on key expiration events
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-params"
  })
}

# ElastiCache Redis Cluster
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${local.name_prefix}-redis"
  description                = "Redis cluster for speed layer signal caching"
  
  # Cluster configuration
  port                = var.redis_port
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  
  # Node configuration
  node_type               = var.redis_node_type
  num_cache_clusters      = var.redis_num_cache_nodes
  
  # Engine configuration
  engine_version          = "7.0"
  
  # Network configuration
  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]
  
  # Security configuration
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token_enabled         = false  # Simplify for MVP, enable later
  
  # Backup configuration
  snapshot_retention_limit = 1  # Keep 1 backup for disaster recovery
  snapshot_window         = "03:00-05:00"  # Early morning backup
  maintenance_window      = "sun:05:00-sun:07:00"  # Sunday morning maintenance
  
  # Automatic failover (only for multi-node)
  automatic_failover_enabled = var.redis_num_cache_nodes > 1
  multi_az_enabled          = var.redis_num_cache_nodes > 1 && var.environment == "prod"
  
  # Performance settings
  apply_immediately = var.environment != "prod"  # Allow immediate changes in non-prod
  
  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow_log.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-cluster"
  })
  
  lifecycle {
    prevent_destroy = true  # Protect production data
  }
}

# CloudWatch Log Group for Redis slow log
resource "aws_cloudwatch_log_group" "redis_slow_log" {
  name              = "/aws/elasticache/redis/${local.name_prefix}/slow-log"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-slow-log"
  })
}

# CloudWatch Alarms for Redis monitoring
resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  count = var.enable_detailed_monitoring ? 1 : 0

  alarm_name          = "${local.name_prefix}-redis-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = "120"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors redis cpu utilization"
  alarm_actions       = []  # Add SNS topic for notifications

  dimensions = {
    CacheClusterId = aws_elasticache_replication_group.redis.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-cpu-alarm"
  })
}

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  count = var.enable_detailed_monitoring ? 1 : 0

  alarm_name          = "${local.name_prefix}-redis-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = "120"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "This metric monitors redis memory utilization"
  alarm_actions       = []  # Add SNS topic for notifications

  dimensions = {
    CacheClusterId = aws_elasticache_replication_group.redis.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-memory-alarm"
  })
}

resource "aws_cloudwatch_metric_alarm" "redis_connections" {
  count = var.enable_detailed_monitoring ? 1 : 0

  alarm_name          = "${local.name_prefix}-redis-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CurrConnections"
  namespace           = "AWS/ElastiCache"
  period              = "120"
  statistic           = "Average"
  threshold           = "80"  # Adjust based on node type limits
  alarm_description   = "This metric monitors redis connection count"
  alarm_actions       = []  # Add SNS topic for notifications

  dimensions = {
    CacheClusterId = aws_elasticache_replication_group.redis.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-connections-alarm"
  })
}
