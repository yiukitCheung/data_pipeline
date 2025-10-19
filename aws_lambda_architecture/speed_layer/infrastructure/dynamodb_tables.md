# DynamoDB Tables for Speed Layer

## 1. Alert Configurations Table

**Table Name:** `alert_configurations`

**Purpose:** Store user-defined alert conditions for real-time signal generation

**Primary Key:**
- Partition Key: `alert_id` (String) - UUID
- Sort Key: None

**Global Secondary Indexes:**
1. **SymbolIndex**
   - Partition Key: `symbol` (String)
   - Sort Key: `user_id` (String)
   - Purpose: Query all alerts for a specific symbol

2. **UserIndex**
   - Partition Key: `user_id` (String)
   - Sort Key: `created_at` (Number) - Unix timestamp
   - Purpose: Query all alerts for a specific user

**Attributes:**
```json
{
  "alert_id": "uuid-string",
  "user_id": "user123",
  "symbol": "AAPL",
  "condition_type": "price_threshold",  // or "indicator", "fundamental"
  "condition": {
    "operator": ">",
    "threshold": 200.00,
    "price_type": "close"  // open, high, low, close
  },
  "notification_method": "sns",  // or "websocket", "email"
  "enabled": true,
  "created_at": 1697654400,
  "updated_at": 1697654400,
  "last_triggered": 1697658000,  // null if never triggered
  "trigger_count": 5
}
```

**Provisioning:**
- Mode: On-Demand (pay-per-request)
- Estimated cost: $10-20/month for MVP

**AWS CLI Creation:**
```bash
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
    "[{
      \"IndexName\": \"SymbolIndex\",
      \"KeySchema\": [{\"AttributeName\":\"symbol\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"user_id\",\"KeyType\":\"RANGE\"}],
      \"Projection\": {\"ProjectionType\":\"ALL\"}
    },
    {
      \"IndexName\": \"UserIndex\",
      \"KeySchema\": [{\"AttributeName\":\"user_id\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"created_at\",\"KeyType\":\"RANGE\"}],
      \"Projection\": {\"ProjectionType\":\"ALL\"}
    }]" \
  --region ca-west-1
```

---

## 2. Real-Time Ticks Table

**Table Name:** `realtime_ticks`

**Purpose:** Store latest tick data for ultra-fast price lookups

**Primary Key:**
- Partition Key: `symbol` (String)
- Sort Key: `timestamp` (Number) - Unix timestamp in milliseconds

**Time-To-Live (TTL):**
- Attribute: `ttl`
- Auto-delete records older than 24 hours

**Attributes:**
```json
{
  "symbol": "AAPL",
  "timestamp": 1697658000123,  // milliseconds
  "price": 205.50,
  "volume": 1000,
  "source": "polygon_websocket",
  "ttl": 1697744400  // Unix timestamp for deletion (24h later)
}
```

**Provisioning:**
- Mode: On-Demand (pay-per-request)
- Estimated cost: $5-10/month for MVP (with TTL auto-cleanup)

**AWS CLI Creation:**
```bash
aws dynamodb create-table \
  --table-name realtime_ticks \
  --attribute-definitions \
    AttributeName=symbol,AttributeType=S \
    AttributeName=timestamp,AttributeType=N \
  --key-schema \
    AttributeName=symbol,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region ca-west-1

# Enable TTL
aws dynamodb update-time-to-live \
  --table-name realtime_ticks \
  --time-to-live-specification \
    "Enabled=true, AttributeName=ttl" \
  --region ca-west-1
```

---

## 3. Alert Notifications History Table

**Table Name:** `alert_notifications_history`

**Purpose:** Audit log of triggered alerts for debugging and analytics

**Primary Key:**
- Partition Key: `user_id` (String)
- Sort Key: `triggered_at` (Number) - Unix timestamp

**Attributes:**
```json
{
  "notification_id": "uuid-string",
  "user_id": "user123",
  "alert_id": "alert-uuid",
  "symbol": "AAPL",
  "current_price": 205.50,
  "threshold": 200.00,
  "triggered_at": 1697658000,
  "notification_method": "sns",
  "delivery_status": "sent",  // or "failed"
  "message_id": "sns-message-id"
}
```

**Provisioning:**
- Mode: On-Demand (pay-per-request)
- Estimated cost: $5-10/month for MVP

**AWS CLI Creation:**
```bash
aws dynamodb create-table \
  --table-name alert_notifications_history \
  --attribute-definitions \
    AttributeName=user_id,AttributeType=S \
    AttributeName=triggered_at,AttributeType=N \
  --key-schema \
    AttributeName=user_id,KeyType=HASH \
    AttributeName=triggered_at,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region ca-west-1
```

---

## Deployment Script

```bash
#!/bin/bash
# deploy_dynamodb_tables.sh

set -e

AWS_REGION=${AWS_REGION:-ca-west-1}

echo "Creating DynamoDB tables in region: $AWS_REGION"

# 1. Alert Configurations
echo "Creating alert_configurations table..."
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

echo "Waiting for alert_configurations table to be active..."
aws dynamodb wait table-exists --table-name alert_configurations --region $AWS_REGION

# 2. Real-Time Ticks
echo "Creating realtime_ticks table..."
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

echo "Waiting for realtime_ticks table to be active..."
aws dynamodb wait table-exists --table-name realtime_ticks --region $AWS_REGION

echo "Enabling TTL on realtime_ticks..."
aws dynamodb update-time-to-live \
  --table-name realtime_ticks \
  --time-to-live-specification "Enabled=true,AttributeName=ttl" \
  --region $AWS_REGION

# 3. Alert Notifications History
echo "Creating alert_notifications_history table..."
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

echo "Waiting for alert_notifications_history table to be active..."
aws dynamodb wait table-exists --table-name alert_notifications_history --region $AWS_REGION

echo "✅ All DynamoDB tables created successfully!"
echo ""
echo "Tables created:"
echo "  - alert_configurations (with SymbolIndex and UserIndex)"
echo "  - realtime_ticks (with TTL enabled)"
echo "  - alert_notifications_history"
echo ""
echo "Total estimated cost: ~$20-40/month (on-demand pricing)"
```

---

## Cost Estimation

| Table | Write Units/month | Read Units/month | Storage | Cost/month |
|-------|------------------|------------------|---------|------------|
| alert_configurations | 10,000 | 100,000 | 1 MB | $2-5 |
| realtime_ticks | 1,000,000 | 500,000 | ~500 MB (with TTL) | $10-15 |
| alert_notifications_history | 50,000 | 20,000 | 10 MB | $3-5 |
| **Total** | | | | **$15-25** |

Note: On-demand pricing automatically scales with usage, so actual costs may vary.

