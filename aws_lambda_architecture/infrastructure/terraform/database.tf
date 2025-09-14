# ===============================================
# Aurora Serverless v2 PostgreSQL Database
# (Replaces TimescaleDB with PostgreSQL + time-series extensions)
# ===============================================

# Subnet group for Aurora
resource "aws_db_subnet_group" "aurora" {
  name       = "${var.project_name}-aurora-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-aurora-subnet-group"
  })
}

# Aurora cluster parameter group
resource "aws_rds_cluster_parameter_group" "aurora" {
  family = "aurora-postgresql14"
  name   = "${var.project_name}-aurora-cluster-params"

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements,pg_hint_plan"
  }

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries taking > 1 second
  }

  tags = local.common_tags
}

# Aurora DB parameter group  
resource "aws_db_parameter_group" "aurora" {
  family = "aurora-postgresql14"
  name   = "${var.project_name}-aurora-db-params"

  tags = local.common_tags
}

# Generate random password for Aurora
resource "random_password" "aurora_password" {
  length  = 32
  special = true
}

# Store Aurora credentials in Secrets Manager
resource "aws_secretsmanager_secret" "aurora_credentials" {
  name        = "${var.project_name}-aurora-credentials"
  description = "Aurora PostgreSQL credentials"

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "aurora_credentials" {
  secret_id = aws_secretsmanager_secret.aurora_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.aurora_password.result
    engine   = "postgres"
    host     = aws_rds_cluster.aurora.endpoint
    port     = aws_rds_cluster.aurora.port
    dbname   = var.db_name
  })
}

# Aurora Serverless v2 Cluster
resource "aws_rds_cluster" "aurora" {
  cluster_identifier = "${var.project_name}-aurora-cluster"
  
  # Database configuration
  engine         = "aurora-postgresql"
  engine_mode    = "provisioned"
  engine_version = "14.9"
  
  database_name   = var.db_name
  master_username = var.db_username
  master_password = random_password.aurora_password.result
  
  # Serverless v2 scaling
  serverlessv2_scaling_configuration {
    max_capacity = var.db_max_capacity
    min_capacity = var.db_min_capacity
  }
  
  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]
  
  # Parameter groups
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.aurora.name
  
  # Backup configuration
  backup_retention_period = var.environment == "prod" ? 7 : 1
  preferred_backup_window = "03:00-04:00"
  
  # Maintenance configuration
  preferred_maintenance_window = "sun:04:00-sun:05:00"
  
  # Security
  storage_encrypted = true
  
  # Deletion protection
  deletion_protection = var.environment == "prod" ? true : false
  skip_final_snapshot = var.environment != "prod"
  
  # Performance Insights
  enabled_cloudwatch_logs_exports = ["postgresql"]
  
  tags = merge(local.common_tags, {
    Name = "${var.project_name}-aurora-cluster"
  })
}

# Aurora Serverless v2 Instance
resource "aws_rds_cluster_instance" "aurora" {
  count              = 1
  cluster_identifier = aws_rds_cluster.aurora.id
  identifier         = "${var.project_name}-aurora-instance-${count.index}"
  
  instance_class = var.db_instance_class
  engine         = aws_rds_cluster.aurora.engine
  engine_version = aws_rds_cluster.aurora.engine_version
  
  db_parameter_group_name = aws_db_parameter_group.aurora.name
  
  # Performance Insights
  performance_insights_enabled = true
  
  # Monitoring
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.aurora_monitoring.arn
  
  tags = merge(local.common_tags, {
    Name = "${var.project_name}-aurora-instance-${count.index}"
  })
}

# IAM role for Aurora monitoring
resource "aws_iam_role" "aurora_monitoring" {
  name = "${var.project_name}-aurora-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "aurora_monitoring" {
  role       = aws_iam_role.aurora_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# Security group for Aurora
resource "aws_security_group" "aurora" {
  name_prefix = "${var.project_name}-aurora-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [
      aws_security_group.lambda_functions.id,
      aws_security_group.ecs_tasks.id
    ]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-aurora-sg"
  })
}

# ===============================================
# Database Initialization Lambda
# ===============================================

# Lambda function to initialize database schema
resource "aws_lambda_function" "db_init" {
  filename         = "db_init.zip"
  function_name    = "${var.project_name}-db-init"
  role            = aws_iam_role.db_init_lambda.arn
  handler         = "index.handler"
  runtime         = "python3.10"
  timeout         = 300

  vpc_config {
    subnet_ids         = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_group_ids = [aws_security_group.lambda_functions.id]
  }

  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.aurora_credentials.arn
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.db_init_lambda_basic,
    aws_iam_role_policy_attachment.db_init_lambda_vpc,
    aws_cloudwatch_log_group.db_init_lambda,
  ]

  tags = local.common_tags
}

# IAM role for database initialization Lambda
resource "aws_iam_role" "db_init_lambda" {
  name = "${var.project_name}-db-init-lambda-role"

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

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "db_init_lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.db_init_lambda.name
}

resource "aws_iam_role_policy_attachment" "db_init_lambda_vpc" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
  role       = aws_iam_role.db_init_lambda.name
}

resource "aws_iam_role_policy" "db_init_lambda_secrets" {
  name = "${var.project_name}-db-init-lambda-secrets"
  role = aws_iam_role.db_init_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.aurora_credentials.arn
      }
    ]
  })
}

# CloudWatch log group for database init Lambda
resource "aws_cloudwatch_log_group" "db_init_lambda" {
  name              = "/aws/lambda/${var.project_name}-db-init"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}
