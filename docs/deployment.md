# Deployment Guide

This guide covers deployment options for both the **Prefect Medallion Architecture** and **AWS Lambda Architecture** implementations.

## 🏗️ Architecture Deployment Options

### Local Development
- **Use Case**: Development, testing, prototyping
- **Implementations**: Both architectures support local development
- **Infrastructure**: Docker containers, local databases

### Production Cloud
- **Use Case**: Production workloads, real-time processing
- **Implementations**: AWS Lambda Architecture (primary), Medallion (backup)
- **Infrastructure**: AWS managed services, serverless

## 📊 Prefect Medallion Architecture Deployment

### Local Development Deployment

#### Prerequisites
```bash
# System requirements
- Python 3.8+
- Docker & Docker Compose
- PostgreSQL 14+
- 8GB+ RAM recommended
```

#### Setup Steps
```bash
# 1. Clone and setup environment
git clone <repository>
cd data_pipeline/prefect_medallion/

# 2. Create virtual environment
python -m venv .dp
source .dp/bin/activate  # Windows: .dp\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Environment configuration
cp ../.env.example ../.env
# Edit .env with your API keys and database credentials

# 5. Database setup (using Docker)
docker run -d \
  --name condvest-timescale \
  -e POSTGRES_DB=condvest \
  -e POSTGRES_USER=yiukitcheung \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  timescale/timescaledb:latest-pg14

# 6. Start Prefect server
prefect server start --host 127.0.0.1 --port 4200

# 7. Run initial pipeline
python flows/make_bronze_pipeline.py
```

### Production Deployment (VM/Server)

#### Docker Compose Deployment
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg14
    environment:
      POSTGRES_DB: condvest
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - timescale_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  redis:
    image: redis:alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "6379:6379"
  
  prefect-server:
    image: prefecthq/prefect:2.0
    command: prefect server start --host 0.0.0.0
    ports:
      - "4200:4200"
    environment:
      PREFECT_API_URL: http://0.0.0.0:4200/api
  
  condvest-medallion:
    build: .
    depends_on:
      - timescaledb
      - redis
      - prefect-server
    environment:
      PREFECT_API_URL: http://prefect-server:4200/api
      POSTGRES_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@timescaledb:5432/condvest
    volumes:
      - ./process/storage:/app/process/storage

volumes:
  timescale_data:
```

#### Deployment Commands
```bash
# Deploy to production server
docker-compose -f docker-compose.prod.yml up -d

# Setup scheduled flows
docker exec condvest-medallion prefect deployment build flows/make_bronze_pipeline.py:bronze_pipeline
docker exec condvest-medallion prefect deployment apply bronze_pipeline-deployment.yaml
```

### Monitoring & Maintenance
```bash
# Health checks
curl http://localhost:4200/api/health

# View logs
docker-compose logs -f condvest-medallion

# Database backups
pg_dump postgresql://user:pass@localhost:5432/condvest > backup.sql

# Clean up old data
psql -d condvest -f database/deletion.sql
```

## ☁️ AWS Lambda Architecture Deployment

### Local Development Deployment

#### Prerequisites
```bash
# System requirements
- Docker & Docker Compose
- AWS CLI configured
- Node.js 16+ (for CDK)
- Python 3.9+
```

#### Local Setup
```bash
# 1. Navigate to AWS architecture
cd data_pipeline/aws_lambda_architecture/

# 2. Start local development environment
cd local_dev/
docker-compose -f minimal-docker-compose.yml up -d

# 3. Run local tests
cd ../tests/
python test_data_fetching.py

# 4. Start local API server
cd ../local_dev/
python local_api_server.py
# Access: http://localhost:8080
```

### AWS Production Deployment

#### Infrastructure Setup (Terraform)
```bash
# 1. Navigate to infrastructure directory
cd aws_lambda_architecture/infrastructure/terraform/

# 2. Initialize Terraform
terraform init

# 3. Plan deployment
terraform plan \
  -var="polygon_api_key=${POLYGON_API_KEY}" \
  -var="environment=production"

# 4. Deploy infrastructure
terraform apply \
  -var="polygon_api_key=${POLYGON_API_KEY}" \
  -var="environment=production"
```

#### Lambda Function Deployment
```bash
# 1. Package Lambda functions
cd aws_lambda_architecture/

# Create deployment packages
./scripts/package_lambdas.sh

# 2. Deploy using AWS CLI
aws lambda update-function-code \
  --function-name condvest-daily-ohlcv-fetcher \
  --zip-file fileb://dist/daily_ohlcv_fetcher.zip

aws lambda update-function-code \
  --function-name condvest-websocket-handler \
  --zip-file fileb://dist/websocket_handler.zip

aws lambda update-function-code \
  --function-name condvest-api-live-prices \
  --zip-file fileb://dist/api_live_prices.zip
```

#### Environment Configuration
```bash
# Set environment variables for Lambda functions
aws lambda update-function-configuration \
  --function-name condvest-daily-ohlcv-fetcher \
  --environment Variables='{
    "POLYGON_API_KEY":"'${POLYGON_API_KEY}'",
    "AURORA_CLUSTER_ARN":"'${AURORA_CLUSTER_ARN}'",
    "AURORA_SECRET_ARN":"'${AURORA_SECRET_ARN}'",
    "DATABASE_NAME":"condvest",
    "BATCH_SIZE":"50"
  }'
```

### Infrastructure Components

#### Core AWS Services
- **Aurora Serverless v2**: Primary database
- **Lambda Functions**: Serverless compute
- **API Gateway**: REST API endpoints
- **EventBridge**: Scheduling and events
- **Kinesis**: Real-time data streaming
- **DynamoDB**: Fast NoSQL storage
- **ElastiCache**: Redis caching
- **S3**: Data lake storage
- **CloudWatch**: Monitoring and logs

#### Estimated Costs (Monthly)
```
Aurora Serverless v2:     $150-300
Lambda (1M requests):     $20-50
API Gateway:              $10-30
Kinesis Data Streams:     $50-100
DynamoDB:                 $25-75
ElastiCache:              $50-150
S3 Storage:               $10-25
CloudWatch:               $10-20
Data Transfer:            $20-50
------------------------
Total Estimated:          $345-800/month
```

### Monitoring & Observability

#### CloudWatch Dashboards
```bash
# Create monitoring dashboard
aws cloudwatch put-dashboard \
  --dashboard-name "Condvest-Trading-Pipeline" \
  --dashboard-body file://monitoring/dashboard.json
```

#### Alerts Setup
```bash
# Lambda error alerts
aws cloudwatch put-metric-alarm \
  --alarm-name "CondvestLambdaErrors" \
  --alarm-description "Lambda function errors" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold
```

#### Log Aggregation
```bash
# View Lambda logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/condvest"

# Tail logs in real-time
aws logs tail /aws/lambda/condvest-daily-ohlcv-fetcher --follow
```

## 🔄 CI/CD Pipeline

### GitHub Actions Workflow
```yaml
# .github/workflows/deploy.yml
name: Deploy Condvest Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-medallion:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Test Medallion Architecture
        run: |
          cd prefect_medallion/
          pip install -r requirements.txt
          python -m pytest test/

  test-lambda:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Test Lambda Architecture
        run: |
          cd aws_lambda_architecture/
          pip install -r requirements.txt
          python tests/test_data_fetching.py

  deploy-aws:
    needs: [test-medallion, test-lambda]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Deploy Infrastructure
        run: |
          cd aws_lambda_architecture/infrastructure/terraform/
          terraform init
          terraform apply -auto-approve
      - name: Deploy Lambda Functions
        run: |
          cd aws_lambda_architecture/
          ./scripts/deploy_lambdas.sh
```

## 🛡️ Security Considerations

### Network Security
- **VPC Configuration**: Lambda functions in private subnets
- **Security Groups**: Restrictive inbound/outbound rules
- **NAT Gateway**: Outbound internet access for API calls

### Data Security
- **Encryption at Rest**: Aurora, DynamoDB, S3 encryption
- **Encryption in Transit**: HTTPS/TLS for all communications
- **Secrets Management**: AWS Secrets Manager for API keys

### Access Control
```bash
# IAM policies for Lambda execution
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "rds-data:ExecuteStatement",
        "rds-data:BatchExecuteStatement"
      ],
      "Resource": "arn:aws:rds:*:*:cluster:condvest-aurora-cluster"
    }
  ]
}
```

## 📈 Scaling Strategies

### Medallion Architecture Scaling
- **Vertical Scaling**: Increase VM resources
- **Horizontal Scaling**: Multiple Prefect agents
- **Database Scaling**: Read replicas, connection pooling

### Lambda Architecture Scaling
- **Auto-scaling**: Built-in Lambda concurrency scaling
- **Aurora Scaling**: Serverless v2 auto-scaling
- **Cache Scaling**: ElastiCache cluster mode

## 🔧 Troubleshooting

### Common Issues
1. **Lambda Timeout**: Increase timeout, optimize queries
2. **Aurora Connection Limits**: Use connection pooling
3. **API Rate Limits**: Implement exponential backoff
4. **Memory Issues**: Increase Lambda memory allocation

### Debug Commands
```bash
# Check Lambda function status
aws lambda get-function --function-name condvest-daily-ohlcv-fetcher

# View CloudWatch logs
aws logs describe-log-streams --log-group-name "/aws/lambda/condvest-daily-ohlcv-fetcher"

# Test Aurora connectivity
aws rds-data execute-statement \
  --resource-arn $AURORA_CLUSTER_ARN \
  --secret-arn $AURORA_SECRET_ARN \
  --database condvest \
  --sql "SELECT 1"
```

## 📚 Additional Resources

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Prefect Documentation](https://docs.prefect.io/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
