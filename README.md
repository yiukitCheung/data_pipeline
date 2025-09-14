# Condvest Trading Analytics - Data Pipeline Implementations

## Overview
This repository contains **two different architectural implementations** for the Condvest Trading Analytics data pipeline:

1. **Medallion Architecture** (`prefect_medallion/`) - Local/traditional implementation with Prefect orchestration
2. **Lambda Architecture** (`aws_lambda_architecture/`) - AWS-native cloud implementation for real-time processing

## 🏗️ Architecture Implementations

### 📁 Prefect Medallion Architecture (`prefect_medallion/`)
Traditional **Bronze → Silver → Gold** data pipeline implementation:
- **Bronze Layer**: Raw data ingestion from Polygon.io
- **Silver Layer**: Data resampling and processing with DuckDB
- **Gold Layer**: Analytics, indicators, and trading signals
- **Orchestration**: Prefect for workflow management
- **Storage**: TimescaleDB + DuckDB + Redis
- **Deployment**: Local/on-premise with Docker

### ☁️ AWS Lambda Architecture (`aws_lambda_architecture/`)
Modern **Batch + Speed + Serving** layer implementation:
- **Batch Layer**: Daily OHLCV processing with AWS services
- **Speed Layer**: Real-time stream processing with Kinesis + Flink
- **Serving Layer**: APIs and caching with API Gateway + Lambda
- **Orchestration**: AWS native services (EventBridge, Step Functions)
- **Storage**: Aurora Serverless + DynamoDB + ElastiCache
- **Deployment**: Serverless AWS infrastructure

## 🚀 Quick Start

### Environment Setup
Both implementations share the same `.env` configuration:

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POLYGON_API_KEY=your_polygon_key
REDIS_PASSWORD=your_redis_password
```

### Prefect Medallion (Local Development)
```bash
cd prefect_medallion/
pip install -r requirements.txt
prefect server start
python flows/make_bronze_pipeline.py
```

### AWS Lambda Architecture (Cloud-Native)
```bash
cd aws_lambda_architecture/

# Local development with Docker
cd local_dev/
docker-compose up

# AWS deployment
cd infrastructure/terraform/
terraform init
terraform apply
```

## 📊 Architecture Comparison

| Feature | Prefect Medallion | AWS Lambda |
|---------|------------------|------------|
| **Latency** | Minutes | Sub-second |
| **Scalability** | Manual scaling | Auto-scaling |
| **Cost** | Fixed infrastructure | Pay-per-use |
| **Complexity** | Medium | Low (managed services) |
| **Real-time** | Batch processing | Stream processing |
| **Deployment** | Local/VM | Serverless cloud |

## 🛠️ Development Workflow

### Branch Strategy
- `main`: Stable releases
- `medallion-dev`: Prefect implementation development
- `lambda-dev`: AWS implementation development
- `feature/*`: Feature branches

### Testing
Each implementation has its own test suite:
```bash
# Medallion tests
cd prefect_medallion/ && pytest

# Lambda tests  
cd aws_lambda_architecture/ && pytest
```

## 📚 Documentation
- [Prefect Medallion Guide](prefect_medallion/README.md)
- [AWS Lambda Architecture Guide](aws_lambda_architecture/README.md)
- [Deployment Guide](docs/deployment.md)
- [API Documentation](docs/api.md)

## 🤝 Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
