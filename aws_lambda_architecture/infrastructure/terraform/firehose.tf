# Kinesis Data Firehose for MVP Speed Layer
# Direct delivery from Kinesis Streams to Aurora Database

resource "aws_kinesis_firehose_delivery_stream" "tick_data_stream" {
  name        = "condvest-tick-data-firehose"
  destination = "http_endpoint"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.tick_stream.arn
    role_arn          = aws_iam_role.firehose_role.arn
  }

  http_endpoint_configuration {
    name               = "condvest-aurora-endpoint"
    url                = var.aurora_http_endpoint
    s3_backup_mode     = "FailedDataOnly"
    retry_duration     = 3600
    
    # Aurora Data API endpoint configuration
    request_configuration {
      content_encoding = "GZIP"
      
      common_attributes = {
        "database" = var.aurora_database_name
        "schema"   = "public"
        "table"    = "raw_ticks"
      }
    }

    # Buffer settings for cost optimization
    buffering_size     = 5    # 5MB buffer
    buffering_interval = 60   # 1 minute buffer

    # Compression for cost savings
    compression_format = "GZIP"

    # S3 backup for failed records
    s3_configuration {
      role_arn           = aws_iam_role.firehose_role.arn
      bucket_arn         = aws_s3_bucket.firehose_backup.arn
      prefix             = "failed-ticks/"
      error_output_prefix = "errors/"
      
      buffering_size     = 10
      buffering_interval = 300
      compression_format = "GZIP"
    }
  }

  tags = {
    Name        = "CondVest Tick Data Stream"
    Environment = var.environment
    Purpose     = "MVP Speed Layer"
  }
}

# Alternative: Direct S3 delivery for even lower costs
resource "aws_kinesis_firehose_delivery_stream" "tick_data_s3_stream" {
  name        = "condvest-tick-data-s3-firehose"
  destination = "extended_s3"

  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.tick_stream.arn
    role_arn          = aws_iam_role.firehose_role.arn
  }

  extended_s3_configuration {
    role_arn           = aws_iam_role.firehose_role.arn
    bucket_arn         = aws_s3_bucket.tick_data_lake.arn
    prefix             = "year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
    error_output_prefix = "errors/"
    
    # Cost-optimized buffering
    buffering_size     = 128  # 128MB buffer
    buffering_interval = 300  # 5 minutes
    
    compression_format = "GZIP"
    
    # Convert JSON to Parquet for analytics
    data_format_conversion_configuration {
      enabled = true
      
      output_format_configuration {
        serializer {
          parquet_ser_de {}
        }
      }
      
      schema_configuration {
        database_name = aws_glue_catalog_database.tick_data.name
        table_name    = aws_glue_catalog_table.tick_data.name
        role_arn      = aws_iam_role.firehose_role.arn
      }
    }

    # Enable CloudWatch logging
    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose_logs.name
      log_stream_name = "tick-data-delivery"
    }
  }

  tags = {
    Name        = "CondVest Tick Data Lake Stream"
    Environment = var.environment
    Purpose     = "MVP Speed Layer - S3 Data Lake"
  }
}

# Kinesis Stream (input from WebSocket Lambda)
resource "aws_kinesis_stream" "tick_stream" {
  name             = "condvest-tick-stream"
  shard_count      = 2  # Start small for MVP
  retention_period = 24 # 24 hours retention

  shard_level_metrics = [
    "IncomingRecords",
    "OutgoingRecords"
  ]

  tags = {
    Name        = "CondVest Tick Stream"
    Environment = var.environment
  }
}

# S3 bucket for data lake (MVP option)
resource "aws_s3_bucket" "tick_data_lake" {
  bucket = "condvest-tick-data-lake-${var.environment}"

  tags = {
    Name        = "CondVest Tick Data Lake"
    Environment = var.environment
    Purpose     = "MVP Raw Tick Storage"
  }
}

# S3 bucket for Firehose backups
resource "aws_s3_bucket" "firehose_backup" {
  bucket = "condvest-firehose-backup-${var.environment}"

  tags = {
    Name        = "CondVest Firehose Backup"
    Environment = var.environment
  }
}

# Glue Data Catalog for S3 analytics
resource "aws_glue_catalog_database" "tick_data" {
  name = "condvest_tick_data"
  
  description = "Tick data for analytics and batch processing"
}

resource "aws_glue_catalog_table" "tick_data" {
  name          = "raw_ticks"
  database_name = aws_glue_catalog_database.tick_data.name
  
  table_type = "EXTERNAL_TABLE"
  
  parameters = {
    "classification"  = "parquet"
    "compressionType" = "gzip"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.tick_data_lake.bucket}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    
    columns {
      name = "symbol"
      type = "string"
    }
    
    columns {
      name = "price"
      type = "decimal(12,4)"
    }
    
    columns {
      name = "volume"
      type = "bigint"
    }
    
    columns {
      name = "timestamp"
      type = "timestamp"
    }
    
    columns {
      name = "exchange"
      type = "string"
    }
  }
  
  partition_keys {
    name = "year"
    type = "string"
  }
  
  partition_keys {
    name = "month"
    type = "string"
  }
  
  partition_keys {
    name = "day"
    type = "string"
  }
}

# IAM role for Firehose
resource "aws_iam_role" "firehose_role" {
  name = "condvest-firehose-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "CondVest Firehose Role"
    Environment = var.environment
  }
}

# IAM policy for Firehose
resource "aws_iam_role_policy" "firehose_policy" {
  name = "condvest-firehose-policy"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:DescribeStream",
          "kinesis:GetShardIterator",
          "kinesis:GetRecords"
        ]
        Resource = aws_kinesis_stream.tick_stream.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.tick_data_lake.arn,
          "${aws_s3_bucket.tick_data_lake.arn}/*",
          aws_s3_bucket.firehose_backup.arn,
          "${aws_s3_bucket.firehose_backup.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetTable",
          "glue:GetTableVersion",
          "glue:GetTableVersions"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents"
        ]
        Resource = aws_cloudwatch_log_group.firehose_logs.arn
      }
    ]
  })
}

# CloudWatch log group for Firehose
resource "aws_cloudwatch_log_group" "firehose_logs" {
  name              = "/aws/kinesisfirehose/condvest-tick-data"
  retention_in_days = 7  # Keep logs for 1 week

  tags = {
    Name        = "CondVest Firehose Logs"
    Environment = var.environment
  }
}

# Outputs
output "kinesis_stream_name" {
  value = aws_kinesis_stream.tick_stream.name
  description = "Name of the Kinesis stream for tick data"
}

output "kinesis_stream_arn" {
  value = aws_kinesis_stream.tick_stream.arn
  description = "ARN of the Kinesis stream for tick data"
}

output "firehose_delivery_stream_name" {
  value = aws_kinesis_firehose_delivery_stream.tick_data_s3_stream.name
  description = "Name of the Firehose delivery stream"
}

output "tick_data_lake_bucket" {
  value = aws_s3_bucket.tick_data_lake.bucket
  description = "S3 bucket for tick data lake"
}
