# ===============================================
# Database Module Outputs
# ===============================================

output "postgres_endpoint" {
  description = "PostgreSQL database endpoint"
  value       = aws_db_instance.postgres.address
}

output "postgres_port" {
  description = "PostgreSQL database port"
  value       = aws_db_instance.postgres.port
}

output "postgres_database_name" {
  description = "PostgreSQL database name"
  value       = aws_db_instance.postgres.db_name
}

output "postgres_username" {
  description = "PostgreSQL master username"
  value       = aws_db_instance.postgres.username
  sensitive   = true
}

output "postgres_secret_arn" {
  description = "ARN of the PostgreSQL credentials secret"
  value       = aws_secretsmanager_secret.postgres_credentials.arn
}

output "postgres_security_group_id" {
  description = "Security group ID for PostgreSQL database"
  value       = aws_security_group.postgres.id
}

output "postgres_subnet_group_name" {
  description = "Database subnet group name"
  value       = aws_db_subnet_group.postgres.name
}

output "postgres_parameter_group_name" {
  description = "Database parameter group name"
  value       = aws_db_parameter_group.postgres.name
}

output "postgres_instance_id" {
  description = "RDS instance identifier"
  value       = aws_db_instance.postgres.id
}

# Additional outputs for database initialization
output "rds_endpoint" {
  description = "RDS database endpoint"
  value       = aws_db_instance.postgres.address
}

output "rds_password" {
  description = "RDS database password"
  value       = random_password.postgres_password.result
  sensitive   = true
}
