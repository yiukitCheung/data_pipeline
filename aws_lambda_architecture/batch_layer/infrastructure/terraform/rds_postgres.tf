# Cost-Effective PostgreSQL on RDS 
# Purpose: Optimized PostgreSQL for stock market time-series data
# Cost: ~$15-30/month vs Aurora's $50-100/month

# RDS Subnet Group
resource "aws_db_subnet_group" "postgres" {
  name       = "${var.environment}-postgres-subnet-group"
  subnet_ids = data.aws_subnets.private.ids

  tags = {
    Name = "${var.environment}-postgres-subnet-group"
  }
}

# Security Group for PostgreSQL
resource "aws_security_group" "postgres" {
  name_prefix = "${var.environment}-postgres-"
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

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Remove this after setup
    description = "Temporary public access for setup"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-postgres-sg"
  }
}

# Random password for PostgreSQL
resource "random_password" "postgres_password" {
  length  = 16
  special = true
}

# Secrets Manager secret for PostgreSQL credentials
resource "aws_secretsmanager_secret" "postgres_credentials" {
  name        = "${var.environment}-postgres-credentials"
  description = "PostgreSQL database credentials"

  tags = {
    Name = "${var.environment}-postgres-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "postgres_credentials" {
  secret_id = aws_secretsmanager_secret.postgres_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.postgres_password.result
    engine   = "postgres"
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = var.database_name
  })
}

# RDS instance for PostgreSQL
resource "aws_db_instance" "postgres" {
  identifier = "${var.environment}-postgres"

  # Engine Configuration
  engine         = "postgres"
  engine_version = var.postgres_engine_version
  instance_class = var.db_instance_class

  # Storage Configuration
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  # Database Configuration
  db_name  = var.database_name
  username = var.db_username
  password = random_password.postgres_password.result

  # Network Configuration
  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  publicly_accessible    = true  # Temporary for setup
  port                   = 5432

  # Backup Configuration
  backup_retention_period = var.backup_retention_period
  backup_window          = "07:00-09:00"  # UTC
  maintenance_window     = "sun:09:00-sun:10:00"  # UTC

  # Parameter Group
  parameter_group_name = aws_db_parameter_group.postgres.name

  # Monitoring
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_enhanced_monitoring.arn

  # Performance Insights
  performance_insights_enabled = true
  performance_insights_retention_period = 7

  # Deletion Protection
  deletion_protection = var.enable_deletion_protection
  skip_final_snapshot = !var.enable_deletion_protection

  # Cost Optimization
  apply_immediately = false

  tags = {
    Name        = "${var.environment}-postgres"
    Environment = var.environment
    Layer       = "batch"
    Database    = "postgres"
  }

  depends_on = [
    aws_cloudwatch_log_group.postgres_logs
  ]
}

# Parameter Group for PostgreSQL optimization
resource "aws_db_parameter_group" "postgres" {
  family = "postgres15"
  name   = "${var.environment}-postgres-params"

  # Memory and performance optimization for stock data
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "max_connections"
    value = "200"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "effective_cache_size"
    value = "1536MB"  # ~75% of available memory for t3.micro
  }

  parameter {
    name  = "random_page_cost"
    value = "1.1"  # SSD optimization
  }

  parameter {
    name  = "checkpoint_completion_target"
    value = "0.9"
  }

  parameter {
    name  = "wal_buffers"
    value = "16MB"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "work_mem"
    value = "4MB"
  }

  # Logging for monitoring
  parameter {
    name  = "log_statement"
    value = "mod"  # Log INSERT, UPDATE, DELETE statements
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries taking more than 1 second
  }

  tags = {
    Name = "${var.environment}-postgres-params"
  }
}

# CloudWatch Log Group for PostgreSQL
resource "aws_cloudwatch_log_group" "postgres_logs" {
  name              = "/aws/rds/instance/${var.environment}-postgres/postgresql"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = {
    Name = "${var.environment}-postgres-logs"
  }
}

# IAM role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_enhanced_monitoring" {
  name = "${var.environment}-rds-enhanced-monitoring"

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

  tags = {
    Name = "${var.environment}-rds-enhanced-monitoring"
  }
}

resource "aws_iam_role_policy_attachment" "rds_enhanced_monitoring" {
  role       = aws_iam_role.rds_enhanced_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# NOTE: Schema initialization is done manually via pgAdmin
# Use the provided schema_init_postgres.sql script
