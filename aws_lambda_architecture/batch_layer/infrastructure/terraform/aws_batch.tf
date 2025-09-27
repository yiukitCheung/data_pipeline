# AWS Batch Infrastructure for Cost-Efficient Resampling
# Purpose: Run Fibonacci resampling jobs using Fargate Spot for 70% cost savings

# Batch Compute Environment (Fargate Spot)
resource "aws_batch_compute_environment" "fibonacci_resampling" {
  compute_environment_name = "${local.name_prefix}-fibonacci-resampling"
  type                    = "MANAGED"
  state                   = "ENABLED"
  service_role           = aws_iam_role.batch_service_role.arn

  compute_resources {
    type                = "FARGATE_SPOT"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    
    # Cost optimization - use Spot instances
    bid_percentage = 50  # Bid up to 50% of On-Demand price
    
    # Compute limits
    max_vcpus = var.batch_max_vcpus
    
    # Network configuration
    subnets = local.subnet_ids
    security_group_ids = [aws_security_group.batch_compute.id]
    
    tags = merge(local.common_tags, {
      Name = "${local.name_prefix}-batch-compute"
    })
  }

  depends_on = [aws_iam_role_policy_attachment.batch_service_role]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-fibonacci-resampling-compute"
  })
}

# Batch Job Queue
resource "aws_batch_job_queue" "fibonacci_resampling" {
  name                 = "${local.name_prefix}-fibonacci-resampling-queue"
  state               = "ENABLED"
  priority            = 1
  compute_environments = [aws_batch_compute_environment.fibonacci_resampling.arn]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-fibonacci-resampling-queue"
  })
}

# ECR Repository for Batch Job
resource "aws_ecr_repository" "fibonacci_resampler" {
  name                 = "${local.name_prefix}-fibonacci-resampler"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-fibonacci-resampler-ecr"
  })
}

# Batch Job Definition
resource "aws_batch_job_definition" "fibonacci_resampling" {
  name = "${local.name_prefix}-fibonacci-resampling"
  type = "container"

  platform_capabilities = ["FARGATE"]

  container_properties = jsonencode({
    image      = "${aws_ecr_repository.fibonacci_resampler.repository_url}:latest"
    vcpus      = var.batch_job_vcpus
    memory     = var.batch_job_memory
    jobRoleArn = aws_iam_role.batch_execution_role.arn
    
    # Environment variables for Fibonacci resampling (3-34)
    environment = [
        {
          name  = "DB_SECRET_ARN"
          value = aws_secretsmanager_secret.timescale_credentials.arn
        },
        {
          name  = "DATABASE_NAME"
          value = var.database_name
        },
        {
          name  = "DB_HOST"
          value = aws_db_instance.timescale.address
        },
      {
        name  = "AWS_REGION"
        value = var.aws_region
      },
      {
        name  = "FIBONACCI_INTERVALS"
        value = join(",", var.fibonacci_intervals)  # "3,5,8,13,21,34"
      },
      {
        name  = "LOOKBACK_DAYS"
        value = tostring(var.fibonacci_lookback_days)  # 300 days
      },
      {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
    ]
    
    # Fargate configuration
    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }
    
    # Network configuration
    networkConfiguration = {
      assignPublicIp = "ENABLED"
    }
    
    # Resource requirements
    resourceRequirements = [
      {
        type  = "VCPU"
        value = tostring(var.batch_job_vcpus)
      },
      {
        type  = "MEMORY"
        value = tostring(var.batch_job_memory)
      }
    ]
    
    # Logging
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch_jobs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "batch"
      }
    }
  })

  retry_strategy {
    attempts = 2
  }

  timeout {
    attempt_duration_seconds = 3600  # 1 hour timeout
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-fibonacci-resampling-job"
  })
}

# Security Group for Batch Compute
resource "aws_security_group" "batch_compute" {
  name_prefix = "${local.name_prefix}-batch-"
  vpc_id      = local.vpc_id
  description = "Security group for Batch compute environment"

  # Outbound internet access for downloading packages and accessing AWS services
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-batch-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# CloudWatch Log Group for Batch Jobs
resource "aws_cloudwatch_log_group" "batch_jobs" {
  name              = "/aws/batch/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-batch-logs"
  })
}

# EventBridge Rule for Daily Scheduling (after market close)
resource "aws_cloudwatch_event_rule" "daily_resampling" {
  name                = "${local.name_prefix}-daily-resampling"
  description         = "Trigger daily OHLCV fetch and Fibonacci resampling after market close"
  schedule_expression = var.daily_schedule_expression  # "cron(15 21 * * MON-FRI *)" for 9:15 PM EST

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-daily-resampling-rule"
  })
}

# EventBridge Target (Batch Job)
resource "aws_cloudwatch_event_target" "batch_resampling" {
  rule      = aws_cloudwatch_event_rule.daily_resampling.name
  target_id = "BatchResamplingTarget"
  arn       = aws_batch_job_queue.fibonacci_resampling.arn
  role_arn  = aws_iam_role.eventbridge_batch_role.arn

  batch_target {
    job_definition = aws_batch_job_definition.fibonacci_resampling.name
    job_name       = "${local.name_prefix}-fibonacci-resampling"
    job_queue      = aws_batch_job_queue.fibonacci_resampling.name
  }

  input = jsonencode({
    job_name = "${local.name_prefix}-fibonacci-resampling-${formatdate("YYYY-MM-DD", timestamp())}"
  })
}

# CloudWatch Alarms for Cost Monitoring
resource "aws_cloudwatch_metric_alarm" "batch_cost_anomaly" {
  count = var.enable_cost_monitoring ? 1 : 0

  alarm_name          = "${local.name_prefix}-batch-high-cost"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "SubmittedJobs"
  namespace           = "AWS/Batch"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"  # Alert if more than 10 jobs submitted in 5 minutes
  alarm_description   = "High number of Batch jobs may indicate cost issues"
  alarm_actions       = []  # Add SNS topic for notifications

  dimensions = {
    JobQueue = aws_batch_job_queue.fibonacci_resampling.name
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-batch-cost-alarm"
  })
}
