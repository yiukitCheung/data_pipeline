#!/bin/bash
# Deploy DynamoDB tables for Speed Layer
# Purpose: Create DynamoDB tables for alert configurations, real-time ticks, and notifications

set -e

AWS_REGION=${AWS_REGION:-ca-west-1}

echo "🚀 Creating DynamoDB tables in region: $AWS_REGION"
echo "================================================================"

# 1. Alert Configurations
echo ""
echo "📋 Creating alert_configurations table..."
aws dynamodb create-table \
  --table-name alert_configurations \
  --attribute-definitions \
    AttributeName=alert_id,AttributeType=S \
    AttributeName=symbol,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
    AttributeName=created_at,AttributeType=N \
  --key-schema \
    AttributeName=alert_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
    "[{\"IndexName\":\"SymbolIndex\",\"KeySchema\":[{\"AttributeName\":\"symbol\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"user_id\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}},{\"IndexName\":\"UserIndex\",\"KeySchema\":[{\"AttributeName\":\"user_id\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"created_at\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}]" \
  --region $AWS_REGION

echo "⏳ Waiting for alert_configurations table to be active..."
aws dynamodb wait table-exists --table-name alert_configurations --region $AWS_REGION
echo "✅ alert_configurations table created"

# 2. Real-Time Ticks
echo ""
echo "📊 Creating realtime_ticks table..."
aws dynamodb create-table \
  --table-name realtime_ticks \
  --attribute-definitions \
    AttributeName=symbol,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
  --key-schema \
    AttributeName=symbol,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION

echo "⏳ Waiting for realtime_ticks table to be active..."
aws dynamodb wait table-exists --table-name realtime_ticks --region $AWS_REGION

echo "🕒 Enabling TTL (24-hour auto-delete) on realtime_ticks..."
aws dynamodb update-time-to-live \
  --table-name realtime_ticks \
  --time-to-live-specification "Enabled=true,AttributeName=ttl" \
  --region $AWS_REGION
echo "✅ realtime_ticks table created with TTL enabled"

# 3. Alert Notifications History
echo ""
echo "📜 Creating alert_notifications_history table..."
aws dynamodb create-table \
  --table-name alert_notifications_history \
  --attribute-definitions \
    AttributeName=user_id,AttributeType=S \
    AttributeName=triggered_at,AttributeType=N \
  --key-schema \
    AttributeName=user_id,KeyType=HASH \
    AttributeName=triggered_at,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION

echo "⏳ Waiting for alert_notifications_history table to be active..."
aws dynamodb wait table-exists --table-name alert_notifications_history --region $AWS_REGION
echo "✅ alert_notifications_history table created"

echo ""
echo "================================================================"
echo "🎉 All DynamoDB tables created successfully!"
echo "================================================================"
echo ""
echo "Tables created:"
echo "  ✓ alert_configurations (with SymbolIndex and UserIndex GSIs)"
echo "  ✓ realtime_ticks (with TTL enabled for 24h auto-cleanup)"
echo "  ✓ alert_notifications_history"
echo ""
echo "📊 Estimated cost: ~$15-25/month (on-demand pricing)"
echo ""
echo "💡 Next steps:"
echo "  1. Deploy signal_generator Lambda function"
echo "  2. Configure SNS topic for alert notifications"
echo "  3. Set up Kinesis Data Streams for real-time ingestion"
echo ""

