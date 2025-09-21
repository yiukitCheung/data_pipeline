# Kinesis Data Streams for Speed Layer
# Purpose: Real-time data streaming for multi-timeframe OHLCV aggregation

# KMS key for Kinesis encryption
resource "aws_kms_key" "kinesis_key" {
  description             = "KMS key for Kinesis streams encryption - Speed Layer"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kinesis-key"
  })
}

resource "aws_kms_alias" "kinesis_key_alias" {
  name          = "alias/${local.name_prefix}-kinesis"
  target_key_id = aws_kms_key.kinesis_key.key_id
}

# Raw market data stream (from ECS WebSocket service)
resource "aws_kinesis_stream" "market_data_raw" {
  name                      = "${local.name_prefix}-market-data-raw"
  shard_count              = var.kinesis_shard_count
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords", "IncomingBytes", "OutgoingBytes"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-raw"
    Purpose = "raw-data-ingestion"
  })
}

# 1-minute OHLCV stream (processed from raw)
resource "aws_kinesis_stream" "market_data_1min" {
  name                      = "${local.name_prefix}-market-data-1min"
  shard_count              = var.kinesis_shard_count
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-1min"
    Purpose = "ohlcv-1min"
  })
}

# 5-minute OHLCV stream
resource "aws_kinesis_stream" "market_data_5min" {
  name                      = "${local.name_prefix}-market-data-5min"
  shard_count              = 1  # Lower volume for aggregated data
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-5min"
    Purpose = "ohlcv-5min"
  })
}

# 15-minute OHLCV stream
resource "aws_kinesis_stream" "market_data_15min" {
  name                      = "${local.name_prefix}-market-data-15min"
  shard_count              = 1
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-15min"
    Purpose = "ohlcv-15min"
  })
}

# 1-hour OHLCV stream
resource "aws_kinesis_stream" "market_data_1hour" {
  name                      = "${local.name_prefix}-market-data-1hour"
  shard_count              = 1
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-1hour"
    Purpose = "ohlcv-1hour"
  })
}

# 2-hour OHLCV stream
resource "aws_kinesis_stream" "market_data_2hour" {
  name                      = "${local.name_prefix}-market-data-2hour"
  shard_count              = 1
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-2hour"
    Purpose = "ohlcv-2hour"
  })
}

# 4-hour OHLCV stream
resource "aws_kinesis_stream" "market_data_4hour" {
  name                      = "${local.name_prefix}-market-data-4hour"
  shard_count              = 1
  retention_period         = var.kinesis_retention_hours
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-market-data-4hour"
    Purpose = "ohlcv-4hour"
  })
}

# Trading signals stream (output from signal detection)
resource "aws_kinesis_stream" "trading_signals" {
  name                      = "${local.name_prefix}-trading-signals"
  shard_count              = 1
  retention_period         = 168  # 7 days for signals
  shard_level_metrics      = ["IncomingRecords", "OutgoingRecords"]
  enforce_consumer_deletion = false

  encryption_type = "KMS"
  kms_key_id      = aws_kms_key.kinesis_key.arn

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-trading-signals"
    Purpose = "trading-signals"
  })
}

# CloudWatch Log Group for Kinesis Analytics
resource "aws_cloudwatch_log_group" "kinesis_analytics_logs" {
  name              = "/aws/kinesis-analytics/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kinesis-analytics-logs"
  })
}

# CloudWatch Log Group for Kinesis stream monitoring
resource "aws_cloudwatch_log_group" "kinesis_streams_logs" {
  name              = "/aws/kinesis-streams/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kinesis-streams-logs"
  })
}
