# ===============================================
# Fetching Component Testing Variables
# ===============================================

variable "environment" {
  description = "Environment name for testing"
  type        = string
  default     = "test"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ca-west-1"
}

variable "polygon_api_key_secret_arn" {
  description = "ARN of the Polygon API key secret"
  type        = string
}
