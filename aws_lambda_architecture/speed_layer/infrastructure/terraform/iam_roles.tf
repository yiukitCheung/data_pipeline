# IAM Roles and Policies for Speed Layer Components
# Purpose: Define secure access permissions for all speed layer services

# ECS Task Execution Role (for container management)
resource "aws_iam_role" "ecs_execution_role" {
  name = "${local.name_prefix}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-execution-role"
  })
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom policy for ECS execution role (ECR access)
resource "aws_iam_role_policy" "ecs_execution_custom" {
  name = "${local.name_prefix}-ecs-execution-custom"
  role = aws_iam_role.ecs_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.websocket_service.arn}:*"
      }
    ]
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task_role" {
  name = "${local.name_prefix}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-task-role"
  })
}

# Kinesis permissions for ECS tasks
resource "aws_iam_role_policy" "ecs_task_kinesis" {
  name = "${local.name_prefix}-ecs-task-kinesis"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:PutRecord",
          "kinesis:PutRecords",
          "kinesis:DescribeStream",
          "kinesis:ListShards"
        ]
        Resource = [
          aws_kinesis_stream.market_data_raw.arn,
          aws_kinesis_stream.trading_signals.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.kinesis_key.arn
      }
    ]
  })
}

# CloudWatch permissions for ECS tasks
resource "aws_iam_role_policy" "ecs_task_cloudwatch" {
  name = "${local.name_prefix}-ecs-task-cloudwatch"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}

# Kinesis Analytics Application Role
resource "aws_iam_role" "kinesis_analytics_role" {
  name = "${local.name_prefix}-kinesis-analytics-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "kinesisanalytics.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kinesis-analytics-role"
  })
}

# Kinesis Analytics permissions
resource "aws_iam_role_policy" "kinesis_analytics_policy" {
  name = "${local.name_prefix}-kinesis-analytics-policy"
  role = aws_iam_role.kinesis_analytics_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:DescribeStream",
          "kinesis:GetShardIterator",
          "kinesis:GetRecords",
          "kinesis:ListShards"
        ]
        Resource = [
          aws_kinesis_stream.market_data_raw.arn,
          aws_kinesis_stream.market_data_1min.arn,
          aws_kinesis_stream.market_data_5min.arn,
          aws_kinesis_stream.market_data_15min.arn,
          aws_kinesis_stream.market_data_1hour.arn,
          aws_kinesis_stream.market_data_2hour.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kinesis:PutRecord",
          "kinesis:PutRecords"
        ]
        Resource = [
          aws_kinesis_stream.market_data_1min.arn,
          aws_kinesis_stream.market_data_5min.arn,
          aws_kinesis_stream.market_data_15min.arn,
          aws_kinesis_stream.market_data_1hour.arn,
          aws_kinesis_stream.market_data_2hour.arn,
          aws_kinesis_stream.market_data_4hour.arn,
          aws_kinesis_stream.trading_signals.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.kinesis_key.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.kinesis_analytics_logs.arn}:*"
      }
    ]
  })
}

# Auto Scaling Role for ECS
resource "aws_iam_role" "ecs_autoscaling_role" {
  count = var.enable_auto_scaling ? 1 : 0
  name  = "${local.name_prefix}-ecs-autoscaling-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "application-autoscaling.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-autoscaling-role"
  })
}

# Auto Scaling policy attachment
resource "aws_iam_role_policy_attachment" "ecs_autoscaling_policy" {
  count      = var.enable_auto_scaling ? 1 : 0
  role       = aws_iam_role.ecs_autoscaling_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSServiceRolePolicy"
}

# Additional auto scaling permissions
resource "aws_iam_role_policy" "ecs_autoscaling_custom" {
  count = var.enable_auto_scaling ? 1 : 0
  name  = "${local.name_prefix}-ecs-autoscaling-custom"
  role  = aws_iam_role.ecs_autoscaling_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:UpdateService",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:GetMetricStatistics",
          "application-autoscaling:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch Events Role (for future scheduled tasks)
resource "aws_iam_role" "cloudwatch_events_role" {
  name = "${local.name_prefix}-cloudwatch-events-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cloudwatch-events-role"
  })
}

# CloudWatch Events permissions
resource "aws_iam_role_policy" "cloudwatch_events_policy" {
  name = "${local.name_prefix}-cloudwatch-events-policy"
  role = aws_iam_role.cloudwatch_events_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:StopTask",
          "ecs:DescribeTasks"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}
