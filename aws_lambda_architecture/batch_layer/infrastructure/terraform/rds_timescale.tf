# Cost-Effective TimescaleDB on RDS PostgreSQL
# Purpose: Optimized for time-series stock data with TimescaleDB extension
# Cost: ~$15-30/month vs Aurora's $50-100/month

# RDS Subnet Group
resource "aws_db_subnet_group" "timescale" {
  name       = "${var.environment}-timescale-subnet-group"
  subnet_ids = data.aws_subnets.private.ids

  tags = {
    Name = "${var.environment}-timescale-subnet-group"
  }
}

# Security Group for TimescaleDB
resource "aws_security_group" "timescale" {
  name_prefix = "${var.environment}-timescale-"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.batch_lambda.id]
    description     = "PostgreSQL access from Lambda"
  }

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.main.cidr_block]
    description = "PostgreSQL access from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-timescale-sg"
  }
}

# Random password for RDS
resource "random_password" "timescale_password" {
  length  = 16
  special = true
}

# Secrets Manager for DB credentials
resource "aws_secretsmanager_secret" "timescale_credentials" {
  name                    = "${var.environment}-timescale-credentials"
  description             = "TimescaleDB credentials for stock data"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.environment}-timescale-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "timescale_credentials" {
  secret_id = aws_secretsmanager_secret.timescale_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.timescale_password.result
    engine   = "postgres"
    host     = aws_db_instance.timescale.address
    port     = 5432
    dbname   = var.database_name
  })
}

# RDS PostgreSQL Instance with TimescaleDB
resource "aws_db_instance" "timescale" {
  identifier = "${var.environment}-timescale"

  # Engine Configuration
  engine         = "postgres"
  engine_version = "15.5"  # TimescaleDB supports PostgreSQL 15
  instance_class = var.db_instance_class

  # Storage Configuration (cost-optimized)
  allocated_storage       = var.db_allocated_storage
  max_allocated_storage   = var.db_max_allocated_storage
  storage_type           = "gp3"  # More cost-effective than gp2
  storage_encrypted      = true
  
  # Database Configuration
  db_name  = var.database_name
  username = var.db_username
  password = random_password.timescale_password.result

  # Network Configuration
  db_subnet_group_name   = aws_db_subnet_group.timescale.name
  vpc_security_group_ids = [aws_security_group.timescale.id]
  publicly_accessible    = false

  # Backup Configuration (cost-optimized)
  backup_retention_period = var.backup_retention_days
  backup_window          = "03:00-04:00"  # Low traffic hours
  maintenance_window     = "sun:04:00-sun:05:00"

  # Performance Configuration
  performance_insights_enabled = var.enable_performance_insights
  monitoring_interval         = var.monitoring_interval

  # Cost Optimization
  skip_final_snapshot = var.skip_final_snapshot
  deletion_protection = var.enable_deletion_protection

  # Enable automated minor version upgrades
  auto_minor_version_upgrade = true

  tags = {
    Name = "${var.environment}-timescale"
    Type = "TimescaleDB"
  }
}

# Parameter Group for TimescaleDB optimization
resource "aws_db_parameter_group" "timescale" {
  family = "postgres15"
  name   = "${var.environment}-timescale-params"

  # TimescaleDB specific parameters
  parameter {
    name  = "shared_preload_libraries"
    value = "timescaledb"
  }

  parameter {
    name  = "max_connections"
    value = "100"  # Adjust based on your needs
  }

  parameter {
    name  = "work_mem"
    value = "16384"  # 16MB for sorting operations
  }

  parameter {
    name  = "maintenance_work_mem"
    value = "131072"  # 128MB for maintenance operations
  }

  parameter {
    name  = "checkpoint_completion_target"
    value = "0.9"
  }

  parameter {
    name  = "wal_buffers"
    value = "16384"  # 16MB
  }

  parameter {
    name  = "default_statistics_target"
    value = "100"
  }

  parameter {
    name  = "random_page_cost"
    value = "1.1"  # Optimized for SSD storage
  }

  tags = {
    Name = "${var.environment}-timescale-params"
  }
}

# Lambda function to initialize TimescaleDB
resource "aws_lambda_function" "timescale_init" {
  filename         = "timescale_init.zip"
  function_name    = "${var.environment}-timescale-init"
  role            = aws_iam_role.lambda_timescale_init.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.10"
  timeout         = 300

  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.timescale_credentials.arn
      DATABASE_NAME = var.database_name
    }
  }

  depends_on = [aws_db_instance.timescale]

  tags = {
    Name = "${var.environment}-timescale-init"
  }
}

# IAM role for TimescaleDB initialization Lambda
resource "aws_iam_role" "lambda_timescale_init" {
  name = "${var.environment}-lambda-timescale-init"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_timescale_init" {
  name = "${var.environment}-lambda-timescale-init"
  role = aws_iam_role.lambda_timescale_init.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.timescale_credentials.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

# Security group for Lambda initialization function
resource "aws_security_group" "lambda_timescale_init" {
  name_prefix = "${var.environment}-lambda-timescale-init-"
  vpc_id      = data.aws_vpc.main.id

  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.timescale.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-lambda-timescale-init-sg"
  }
}

