# Redis ElastiCache Deployment Guide

## Purpose

Redis ElastiCache provides ultra-fast caching (<1ms latency) for:
- Latest price data from speed layer
- Real-time signal status
- User alert configurations
- Session data

## Architecture

```
Speed Layer → Lambda → ElastiCache Redis → Serving Layer → Frontend
                      (cache latest prices)    (sub-1ms reads)
```

## Configuration

### Instance Type

**For MVP:**
- Instance: `cache.t3.micro`
- Memory: 0.5 GB
- vCPUs: 2
- Network: Up to 5 Gbps
- Cost: ~$12/month

**For Production:**
- Instance: `cache.r6g.large` (recommended)
- Memory: 13.07 GB
- vCPUs: 2
- Network: Up to 10 Gbps
- Cost: ~$100/month

### Engine Version

- Redis 7.0 or later (for improved performance)
- Cluster mode: Disabled (single node for MVP)

### Availability

- Single AZ for MVP (to reduce costs)
- Multi-AZ with automatic failover for production

## Deployment via AWS Console

### Step 1: Create Redis Cluster

1. Go to **ElastiCache** → **Redis clusters** → **Create Redis cluster**
2. Configure:
   - **Cluster mode**: Disabled
   - **Name**: `condvest-price-cache`
   - **Location**: AWS Cloud
   - **Multi-AZ**: Disabled (for MVP)
   - **Engine version**: Redis 7.0
   - **Port**: 6379 (default)
   - **Node type**: cache.t3.micro
   - **Number of replicas**: 0 (for MVP)

### Step 2: Configure Subnet Group

1. **Subnet group**: Create new
   - **Name**: `condvest-cache-subnet-group`
   - **Description**: "Subnet group for condvest Redis cache"
   - **VPC**: Select your VPC
   - **Subnets**: Select at least 2 subnets in different AZs

### Step 3: Configure Security

1. **Security groups**: Create new or select existing
   - **Name**: `condvest-redis-sg`
   - **Inbound rules**:
     - Type: Custom TCP
     - Port: 6379
     - Source: Lambda security group, ECS security group
2. **Encryption**:
   - At rest: Enabled (recommended)
   - In transit: Enabled (recommended)

### Step 4: Configure Backup

- **Automatic backups**: Disabled (for MVP to save costs)
- For production: Enable with 7-day retention

### Step 5: Create Cluster

- Review settings
- Click **Create**
- Wait ~10 minutes for cluster to be available

## Deployment via AWS CLI

```bash
#!/bin/bash
# Create Redis ElastiCache cluster

AWS_REGION=${AWS_REGION:-ca-west-1}
VPC_ID="vpc-xxxxx"  # Replace with your VPC ID
SUBNET_IDS=("subnet-xxxxx" "subnet-yyyyy")  # Replace with your subnet IDs

echo "Creating Redis ElastiCache cluster..."

# 1. Create subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name condvest-cache-subnet-group \
  --cache-subnet-group-description "Subnet group for condvest Redis cache" \
  --subnet-ids ${SUBNET_IDS[@]} \
  --region $AWS_REGION

# 2. Create security group
SG_ID=$(aws ec2 create-security-group \
  --group-name condvest-redis-sg \
  --description "Security group for condvest Redis cache" \
  --vpc-id $VPC_ID \
  --region $AWS_REGION \
  --query 'GroupId' \
  --output text)

echo "Created security group: $SG_ID"

# 3. Add inbound rule for Redis port
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 6379 \
  --source-group $LAMBDA_SG_ID \
  --region $AWS_REGION

# 4. Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id condvest-price-cache \
  --engine redis \
  --engine-version 7.0 \
  --cache-node-type cache.t3.micro \
  --num-cache-nodes 1 \
  --cache-subnet-group-name condvest-cache-subnet-group \
  --security-group-ids $SG_ID \
  --region $AWS_REGION

echo "Redis cluster creation initiated. This will take ~10 minutes."
echo "Check status with: aws elasticache describe-cache-clusters --cache-cluster-id condvest-price-cache --region $AWS_REGION"
```

## Redis Data Schema

### 1. Latest Prices

**Key Pattern:** `price:{symbol}`

**Value (Hash):**
```json
{
  "close": "205.50",
  "open": "203.00",
  "high": "206.00",
  "low": "202.50",
  "volume": "1000000",
  "timestamp": "1697658000",
  "source": "speed_layer"
}
```

**TTL:** 5 minutes (auto-expire if speed layer stops updating)

**Usage:**
```python
# Set price
redis_client.hset("price:AAPL", mapping={
    "close": "205.50",
    "timestamp": "1697658000"
})
redis_client.expire("price:AAPL", 300)  # 5 minutes

# Get price
price_data = redis_client.hgetall("price:AAPL")
```

### 2. Latest Signals

**Key Pattern:** `signal:{symbol}:{strategy_id}`

**Value (String - JSON):**
```json
{
  "signal": "buy",
  "confidence": 0.85,
  "timestamp": "1697658000",
  "price": "205.50",
  "indicators": {
    "rsi": 45.2,
    "macd": "bullish"
  }
}
```

**TTL:** 1 hour

### 3. Alert Status

**Key Pattern:** `alert:status:{alert_id}`

**Value (String):**
```
"triggered"  # or "pending", "disabled"
```

**TTL:** 24 hours

### 4. User Session Data

**Key Pattern:** `session:{user_id}`

**Value (Hash):**
```json
{
  "active_symbols": "AAPL,MSFT,GOOGL",
  "last_active": "1697658000",
  "websocket_connected": "true"
}
```

**TTL:** 30 minutes

## Python Client Example

```python
import redis
import json
import os

# Initialize Redis client
redis_client = redis.Redis(
    host=os.environ.get('REDIS_ENDPOINT', 'localhost'),
    port=6379,
    decode_responses=True,
    ssl=True  # Enable SSL for production
)

# Set latest price
def cache_latest_price(symbol, price_data):
    key = f"price:{symbol}"
    redis_client.hset(key, mapping=price_data)
    redis_client.expire(key, 300)  # 5 minutes TTL

# Get latest price
def get_latest_price(symbol):
    key = f"price:{symbol}"
    return redis_client.hgetall(key)

# Cache signal
def cache_signal(symbol, strategy_id, signal_data):
    key = f"signal:{symbol}:{strategy_id}"
    redis_client.setex(
        key,
        3600,  # 1 hour TTL
        json.dumps(signal_data)
    )

# Get signal
def get_signal(symbol, strategy_id):
    key = f"signal:{symbol}:{strategy_id}"
    data = redis_client.get(key)
    return json.loads(data) if data else None
```

## Lambda Environment Variables

Add to all Lambda functions that use Redis:

```
REDIS_ENDPOINT=condvest-price-cache.xxxxxx.cache.amazonaws.com
REDIS_PORT=6379
REDIS_SSL=true
```

## Monitoring

### CloudWatch Metrics

Key metrics to monitor:
- `CPUUtilization`: Should be < 70%
- `NetworkBytesIn/Out`: Network traffic
- `CacheHits`: Cache hit rate (target: >90%)
- `CacheMisses`: Cache miss rate
- `Evictions`: Keys evicted due to memory pressure

### Alarms

Create CloudWatch alarms for:
1. CPU > 80% for 5 minutes
2. Evictions > 1000 per minute
3. Cache hit rate < 80%

## Cost Optimization

### MVP (cache.t3.micro)
- **Cost**: ~$12/month
- **Good for**: 100-1,000 users
- **Memory**: 0.5 GB

### Scale-up Strategy

When to upgrade:
- CPU > 70% sustained
- Memory > 80% used
- Evictions occurring frequently

Next tier: `cache.t3.small` (~$25/month, 1.37 GB memory)

## Connection Pooling

For Lambda functions:
- Use connection pooling to avoid connection overhead
- Reuse Redis client across invocations
- Set socket timeout to 5 seconds

```python
# Global variable (reused across Lambda invocations)
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=os.environ['REDIS_ENDPOINT'],
            port=6379,
            decode_responses=True,
            ssl=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            connection_pool=redis.ConnectionPool(
                max_connections=10
            )
        )
    return _redis_client
```

## Security Best Practices

1. **Enable encryption**:
   - At rest: Yes
   - In transit: Yes (SSL/TLS)

2. **VPC placement**:
   - Always deploy in private subnet
   - Never expose publicly

3. **Security groups**:
   - Only allow access from Lambda/ECS security groups
   - No public access

4. **Authentication**:
   - Use Redis AUTH token (optional for MVP)
   - Rotate credentials regularly

## Estimated Costs

| Configuration | Instance | Monthly Cost |
|---------------|----------|--------------|
| MVP | cache.t3.micro | $12 |
| Small | cache.t3.small | $25 |
| Medium | cache.t3.medium | $50 |
| Large (recommended prod) | cache.r6g.large | $100 |

## Next Steps

1. ✅ Create Redis cluster via AWS Console or CLI
2. ✅ Note the endpoint URL
3. ✅ Update Lambda environment variables
4. ✅ Deploy Redis client code to Lambda functions
5. ✅ Test connection and caching
6. ✅ Monitor CloudWatch metrics

