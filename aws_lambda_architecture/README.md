# AWS Lambda Architecture Implementation

## Overview
This directory contains the AWS-native implementation of the Condvest data pipeline using **Lambda Architecture** pattern for real-time financial data processing.

## Architecture Components

### 📊 Data Sources
- **Polygon.io REST API**: Daily OHLCV data fetching
- **Polygon.io WebSocket**: Real-time tick data streaming

### ⏱️ Batch Layer
- **AWS Lambda Functions**: Daily data processing jobs
- **Amazon Aurora Serverless**: TimescaleDB-compatible storage
- **AWS Batch**: Heavy processing workloads
- **S3**: Data lake storage

### ⚡ Speed Layer
- **Amazon Kinesis Data Streams**: Real-time data ingestion
- **Amazon Kinesis Analytics**: Apache Flink SQL for stream processing
- **AWS Lambda**: Event-driven signal generation
- **Amazon DynamoDB**: Fast tick data storage with TTL

### 🗃️ Serving Layer
- **Amazon ElastiCache (Redis)**: Ultra-fast cache for OHLCV and signals
- **Amazon API Gateway**: RESTful APIs for data access
- **AWS Lambda**: API backend functions
- **Amazon CloudFront**: Global CDN for low-latency access

## Directory Structure

```
aws_lambda_architecture/
├── infrastructure/          # Infrastructure as Code
│   ├── terraform/          # Terraform configurations
│   └── cloudformation/     # CloudFormation templates
├── batch_layer/            # Daily batch processing
│   ├── lambda_functions/   # Lambda function code
│   └── ecs_tasks/         # Heavy processing tasks
├── speed_layer/           # Real-time stream processing
│   ├── kinesis_analytics/ # Flink SQL queries
│   └── lambda_functions/  # Event-driven functions
├── serving_layer/         # API and data serving
│   ├── api_gateway/       # API Gateway configurations
│   └── lambda_functions/  # API backend functions
├── shared/               # Common utilities
│   ├── utils/           # Shared utility functions
│   ├── models/          # Data models and schemas
│   └── clients/         # AWS service clients
├── local_dev/           # Local development environment
├── tests/              # Unit and integration tests
└── docs/               # Documentation
```

## Key Benefits

1. **Serverless-First**: Pay only for what you use
2. **Auto-Scaling**: Handle traffic spikes automatically
3. **Managed Services**: Minimal operational overhead
4. **Real-Time Processing**: Sub-second signal generation
5. **Cost-Optimized**: Estimated ~$300-500/month for MVP scale
6. **Global Access**: CloudFront distribution for worldwide users

## Getting Started

1. **Local Development**: Use `docker-compose` for local testing
2. **Infrastructure**: Deploy AWS resources with Terraform
3. **Deployment**: Use AWS CDK or Serverless Framework
4. **Monitoring**: Built-in CloudWatch metrics and alarms

## Environment Variables

Shared with the parent project via `../.env` file.

## Deployment

See `docs/deployment.md` for detailed deployment instructions.
