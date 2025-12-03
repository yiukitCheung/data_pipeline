# Batch Layer - AWS Lambda Architecture

This directory contains the batch processing layer for the Condvest data pipeline, implementing a Lambda Architecture pattern for financial data processing.

## 📁 Directory Structure

```
batch_layer/
├── database/                    # Database schemas and migrations
│   ├── schemas/                 # PostgreSQL/TimescaleDB table definitions
│   │   └── schema_init_postgres.sql
│   └── migrations/              # Database migration scripts
│
├── fetching/                    # Lambda functions for data fetching
│   ├── lambda_functions/        # Lambda function code
│   │   ├── daily_ohlcv_fetcher.py   # Daily OHLCV data fetcher
│   │   └── daily_meta_fetcher.py    # Symbol metadata fetcher
│   └── deployment_packages/     # Deployment artifacts
│       ├── build_layer.sh            # Build Lambda Layer
│       ├── build_packages.sh         # Build Lambda ZIP packages
│       ├── deploy_lambda.sh          # Deploy Lambda to AWS
│       └── layer_requirements.txt    # Lambda Layer dependencies
│
├── processing/                  # AWS Batch processing jobs
│   └── batch_jobs/             # Batch job Python scripts
│       ├── resampler.py            # Fibonacci resampling (3d,5d,8d,13d,21d,34d)
│       ├── consolidate.py          # Merge date=*.parquet → data.parquet
│       ├── vaccume.py              # Clean up old date=*.parquet files
│       └── requirements.txt        # Python dependencies
│
├── shared/                      # Shared utilities and clients
│   ├── clients/                 # Database and API clients
│   │   ├── s3_client.py
│   │   ├── rds_client.py
│   │   └── polygon_client.py
│   ├── models/                  # Data models
│   └── utils/                   # Utility functions
│
├── local_dev/                   # Local development/testing
│   ├── docker-compose.yml
│   └── local_resampler.sh
│
├── BATCH_LAYER_IMPLEMENTATION_SUMMARY.md  # Detailed implementation docs
└── README.md                    # This file
```

---

## 🧩 Components Overview

### 1. Lambda Fetchers (Daily Data Ingestion)

| Function | File | Purpose | Schedule |
|----------|------|---------|----------|
| **OHLCV Fetcher** | `daily_ohlcv_fetcher.py` | Fetch daily OHLCV from Polygon API | 4:05 PM ET |
| **Meta Fetcher** | `daily_meta_fetcher.py` | Fetch symbol metadata | Daily |

**Output Path:**
```
s3://dev-condvest-datalake/bronze/raw_ohlcv/symbol=AAPL/date=2025-11-19.parquet
```

### 2. Batch Processing Jobs

| Job | File | Purpose | When to Run |
|-----|------|---------|-------------|
| **Consolidator** | `consolidate.py` | Merge daily files → `data.parquet` | Weekly |
| **Vacuum** | `vaccume.py` | Clean old date files (keep 30 days) | Monthly |
| **Resampler** | `resampler.py` | Fibonacci resampling to Silver layer | After consolidation |

---

## 🚀 Quick Start

### Prerequisites
- AWS Account with configured CLI
- Docker installed
- Python 3.11+
- Virtual environment (`.dp`)

### Local Development

```bash
# Activate virtual environment
source .dp/bin/activate

# Run consolidation locally
cd processing/batch_jobs
python consolidate.py --symbols AAPL,MSFT

# Run vacuum with dry-run
python vaccume.py --dry-run --symbols AAPL,MSFT

# Run resampler locally
python resampler.py
```

### AWS Deployment

#### Deploy Lambda Functions
```bash
cd fetching/deployment_packages
./deploy_lambda.sh daily-ohlcv-fetcher
./deploy_lambda.sh daily-meta-fetcher
```

#### Build & Push Docker for Batch Jobs
```bash
cd processing
docker build -t condvest-batch-resampler .
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.ca-west-1.amazonaws.com
docker tag condvest-batch-resampler:latest <account>.dkr.ecr.ca-west-1.amazonaws.com/condvest-batch-resampler:latest
docker push <account>.dkr.ecr.ca-west-1.amazonaws.com/condvest-batch-resampler:latest
```

---

## 📊 Data Flow

```
                    ┌─────────────────┐
                    │  Polygon API    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Lambda Fetcher  │
                    │ (Daily 4:05 PM) │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────▼────────┐          ┌────────▼────────┐
     │       RDS       │          │   S3 Bronze     │
     │   (3yr cache)   │          │ date=*.parquet  │
     └─────────────────┘          └────────┬────────┘
                                           │
                                  ┌────────▼────────┐
                                  │  Consolidator   │
                                  │   (Weekly)      │
                                  └────────┬────────┘
                                           │
                                  ┌────────▼────────┐
                                  │   S3 Bronze     │
                                  │ data.parquet    │
                                  └────────┬────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                 ┌────────▼────┐   ┌───────▼──────┐  ┌──────▼─────┐
                 │   Vacuum    │   │  Resampler   │  │ Analytics  │
                 │  (Monthly)  │   │   (Weekly)   │  │  (DuckDB)  │
                 └─────────────┘   └───────┬──────┘  └────────────┘
                                           │
                                  ┌────────▼────────┐
                                  │   S3 Silver     │
                                  │ 3d,5d,8d,13d... │
                                  └─────────────────┘
```

---

## 🔧 Configuration

### Environment Variables

```bash
# AWS
AWS_REGION=ca-west-1

# S3
S3_BUCKET=dev-condvest-datalake
S3_PREFIX=bronze/raw_ohlcv

# RDS (for watermark tracking)
RDS_HOST=xxx.rds.amazonaws.com
RDS_DATABASE=condvest
RDS_USER=postgres
RDS_PASSWORD=xxx

# Secrets Manager ARNs (for Lambda)
POLYGON_API_KEY_SECRET_ARN=arn:aws:secretsmanager:ca-west-1:xxx
RDS_SECRET_ARN=arn:aws:secretsmanager:ca-west-1:xxx
```

---

## 📝 Job Usage

### Consolidation Job

```bash
# Run on all symbols (first run will take ~6 hours)
python consolidate.py

# Run on specific symbols
python consolidate.py --symbols AAPL,MSFT,GOOGL

# Force full reconsolidation (ignore metadata)
python consolidate.py --force-full
```

### Vacuum/Cleanup Job

```bash
# Dry run (see what would be deleted)
python vaccume.py --dry-run

# Run on specific symbols
python vaccume.py --symbols AAPL,MSFT,GOOGL

# Run full cleanup
python vaccume.py

# Custom retention period (default: 30 days)
python vaccume.py --retention-days 60
```

### Resampler Job

```bash
# Run all Fibonacci intervals
python resampler.py

# Run with force full resample
python resampler.py --force-full

# Environment variables
export RESAMPLING_INTERVALS="3,5,8,13,21,34"
python resampler.py
```

---

## 📊 S3 Data Structure

### Bronze Layer (Raw Data)
```
s3://dev-condvest-datalake/bronze/raw_ohlcv/
├── symbol=AAPL/
│   ├── data.parquet           # Consolidated (used by resampler)
│   ├── date=2025-11-19.parquet # Daily incremental (recent 30 days)
│   ├── date=2025-11-20.parquet
│   └── ...
├── symbol=MSFT/
│   └── ...
└── symbol=.../
```

### Silver Layer (Resampled)
```
s3://dev-condvest-datalake/silver/
├── silver_3d/
│   └── year=2025/month=11/data_3d_202511.parquet
├── silver_5d/
├── silver_8d/
├── silver_13d/
├── silver_21d/
└── silver_34d/
```

### Processing Metadata
```
s3://dev-condvest-datalake/processing_metadata/
├── consolidation_manifest.parquet  # Tracks consolidated symbols
├── cleanup_manifest.json           # Tracks cleanup history
├── silver_3d_checkpoint.json       # Resampler checkpoints
├── silver_5d_checkpoint.json
└── ...
```

---

## 📚 Additional Documentation

- [**BATCH_LAYER_IMPLEMENTATION_SUMMARY.md**](./BATCH_LAYER_IMPLEMENTATION_SUMMARY.md) - Detailed implementation docs
- [**../README.md**](../README.md) - AWS Lambda Architecture overview

---

## 💰 Estimated Costs

| Component | Monthly Cost |
|-----------|--------------|
| Lambda (fetchers) | ~$1-5 |
| RDS (t3.micro) | ~$15-20 |
| S3 Storage | ~$5-10 |
| AWS Batch (Fargate Spot) | ~$5-10 |
| **Total** | **~$30-50/month** |

---

**Last Updated:** December 3, 2025
