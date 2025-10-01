# Batch Layer - Manual AWS Deployment

This directory contains the application code for the batch processing layer. **Terraform infrastructure has been removed** - you will deploy AWS services manually via AWS Console or CLI.

## 📁 Directory Structure

```
batch_layer/
├── database/              # Database schemas and migrations
│   ├── schemas/          # PostgreSQL/TimescaleDB table definitions
│   └── migrations/       # Database migration scripts
│
├── fetching/             # Lambda functions for data fetching
│   ├── lambda_functions/ # Lambda function code
│   │   ├── daily_ohlcv_fetcher.py
│   │   └── daily_meta_fetcher.py
│   └── deployment_packages/  # Deployment artifacts
│       ├── build_layer.sh         # Build Lambda Layer
│       ├── build_packages.sh      # Build Lambda ZIP packages
│       └── layer_requirements.txt # Lambda Layer dependencies
│
├── processing/           # AWS Batch processing jobs
│   ├── batch_jobs/      # Batch job Python scripts
│   │   └── resampler.py
│   └── container_images/ # Docker images for Batch
│       ├── Dockerfile
│       ├── build_container.sh
│       └── requirements.txt
│
├── shared/              # Shared utilities and clients
│   ├── clients/        # Database and API clients
│   ├── models/         # Data models
│   └── utils/          # Utility functions
│
└── local_dev/          # Local development/testing
    ├── docker-compose.yml
    └── local_resampler.sh
```

## 🚀 Manual Deployment Guide

### Prerequisites
- AWS Account with appropriate permissions
- AWS CLI configured
- Docker installed (for Batch jobs and Lambda layers)
- Python 3.11

---

### Step 1: Create RDS PostgreSQL Database

**Via AWS Console:**
1. Go to RDS → Create Database
2. Choose PostgreSQL (version 15+)
3. Configure:
   - Instance: `db.t3.micro` (or as needed)
   - Database name: `condvest`
   - Master username: Choose your username
   - Enable VPC access
4. Note the endpoint and credentials

**Initialize Database:**
```bash
# Connect to your RDS instance
psql -h <your-rds-endpoint> -U <username> -d condvest

# Run the schema
\i database/schemas/schema_init_postgres.sql
```

---

### Step 2: Create Secrets in AWS Secrets Manager

**Polygon API Key:**
```bash
aws secretsmanager create-secret \
  --name prod/Condvest/PolygonAPI \
  --secret-string '{"api_key":"YOUR_POLYGON_API_KEY"}' \
  --region ca-west-1
```

**RDS Credentials:**
```bash
aws secretsmanager create-secret \
  --name prod/Condvest/RDS-Credentials \
  --secret-string '{"username":"YOUR_DB_USER","password":"YOUR_DB_PASSWORD","host":"YOUR_RDS_ENDPOINT","port":"5432","dbname":"condvest"}' \
  --region ca-west-1
```

---

### Step 3: Build and Deploy Lambda Layer

**Build the Lambda Layer (with Linux binaries):**
```bash
cd fetching/deployment_packages
./build_layer.sh --publish
```

This will:
- Install dependencies (pandas, numpy, yfinance, polygon, etc.) for Linux
- Package shared modules
- Create a ZIP file
- Publish to AWS Lambda Layer

**Note the Layer ARN** - you'll need it for Lambda functions.

---

### Step 4: Build and Deploy Lambda Functions

**Build Lambda packages:**
```bash
cd fetching/deployment_packages
./build_packages.sh
```

**Deploy via AWS Console:**
1. Go to Lambda → Create Function
2. Create `daily-ohlcv-fetcher`:
   - Runtime: Python 3.11
   - Upload `daily_ohlcv_fetcher.zip`
   - Add the Lambda Layer (from Step 3)
   - Set environment variables:
     - `POLYGON_API_KEY_SECRET_ARN`
     - `RDS_SECRET_ARN`
     - `DATABASE_NAME=condvest`
   - Configure VPC (same as RDS)
   - Set timeout: 300 seconds
   - Set memory: 512 MB

3. Repeat for `daily-meta-fetcher`

**Or deploy via AWS CLI:**
```bash
aws lambda create-function \
  --function-name daily-ohlcv-fetcher \
  --runtime python3.11 \
  --role <your-lambda-execution-role-arn> \
  --handler daily_ohlcv_fetcher.lambda_handler \
  --zip-file fileb://deployment_packages/daily_ohlcv_fetcher.zip \
  --layers <your-layer-arn> \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{POLYGON_API_KEY_SECRET_ARN=<arn>,RDS_SECRET_ARN=<arn>,DATABASE_NAME=condvest}" \
  --region ca-west-1
```

---

### Step 5: Create IAM Role for Lambda

**Lambda Execution Role needs:**
- `AWSLambdaVPCAccessExecutionRole` (for VPC access)
- Custom policy to access Secrets Manager:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": [
        "arn:aws:secretsmanager:ca-west-1:*:secret:prod/Condvest/*"
      ]
    }
  ]
}
```

---

### Step 6: Build and Deploy AWS Batch Job

**Build Docker container:**
```bash
cd processing/container_images
./build_container.sh
```

This will:
- Build Docker image with all dependencies
- Push to Amazon ECR

**Create Batch Compute Environment, Job Queue, and Job Definition via Console:**
1. ECR → Create repository: `condvest-batch-resampler`
2. Batch → Compute Environments → Create
3. Batch → Job Queues → Create (attach compute environment)
4. Batch → Job Definitions → Create:
   - Type: Fargate
   - Image: Your ECR image URI
   - vCPUs: 2
   - Memory: 4096 MB
   - Environment variables: Same as Lambda

---

### Step 7: Schedule Lambda Functions with EventBridge

**Create EventBridge Rules:**
```bash
# Daily OHLCV fetch (4:05 PM EST = 9:05 PM UTC)
aws events put-rule \
  --name daily-ohlcv-fetch \
  --schedule-expression "cron(5 21 * * ? *)" \
  --region ca-west-1

aws events put-targets \
  --rule daily-ohlcv-fetch \
  --targets "Id"="1","Arn"="<your-lambda-arn>" \
  --region ca-west-1
```

---

## 🧪 Local Testing

**Test with local PostgreSQL:**
```bash
cd local_dev
docker-compose up -d
python local_resampler.py
```

---

## 📝 Notes

- All Terraform infrastructure has been removed for manual deployment
- You have full control over AWS resource configuration
- Estimated costs (with minimal usage):
  - RDS db.t3.micro: ~$15/month
  - Lambda: Free tier covers most usage
  - Batch (Fargate Spot): $0.01-0.10/job

---

## 🔧 Build Scripts

- `fetching/deployment_packages/build_layer.sh` - Build Lambda Layer
- `fetching/deployment_packages/build_packages.sh` - Build Lambda deployment packages
- `processing/container_images/build_container.sh` - Build Batch Docker container

---

## 📚 Resources

- [AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html)
- [AWS Batch](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html)
- [RDS PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
- [EventBridge Scheduling](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html)
