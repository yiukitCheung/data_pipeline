# Batch Layer

Batch processing layer for the Condvest data pipeline, implementing the Lambda Architecture pattern for financial market data.

## Overview

The batch layer handles high-throughput ingestion and processing of daily stock market data from Polygon.io, storing raw data in a Bronze layer (S3) and generating Fibonacci-resampled analytics in a Silver layer.

## Architecture

```
Polygon.io API
      │
      ├── Lambda: OHLCV Fetcher ──► S3 Bronze (raw_ohlcv/)
      │                           ► RDS (watermark tracking)
      │
      └── Lambda: Meta Fetcher ──► RDS (symbol_metadata)
                │
                ▼
        AWS Batch: Consolidator ──► S3 Bronze (data.parquet)
                │
                ▼
        AWS Batch: Resampler ──► S3 Silver (3d, 5d, 8d, 13d, 21d, 34d)
```

## Components

### Data Ingestion (Lambda Functions)

| Component | Description |
|-----------|-------------|
| **OHLCV Fetcher** | Fetches daily OHLCV data for 5,000+ symbols with async concurrency |
| **Meta Fetcher** | Fetches symbol metadata (name, sector, market cap) |

### Data Processing (AWS Batch Jobs)

| Component | Description |
|-----------|-------------|
| **Consolidator** | Merges daily partition files into consolidated Parquet per symbol |
| **Resampler** | Generates Fibonacci-interval OHLCV aggregations (3d, 5d, 8d, 13d, 21d, 34d) |

### Orchestration (Step Functions)

A Step Functions state machine orchestrates the daily pipeline:

1. **Stage 1**: Parallel execution of OHLCV + Meta fetchers
2. **Stage 2**: Consolidator (waits for Stage 1)
3. **Stage 3**: Parallel execution of 6 resampler intervals

## Data Structure

### S3 Data Lake

```
s3://dev-condvest-datalake/
├── bronze/raw_ohlcv/
│   └── symbol={SYMBOL}/
│       ├── data.parquet           # Consolidated
│       └── date=YYYY-MM-DD.parquet # Daily incremental
│
├── silver/
│   ├── silver_3d/
│   │   └── year=YYYY/month=MM/data_3d_YYYYMM.parquet
│   ├── silver_5d/
│   ├── silver_8d/
│   ├── silver_13d/
│   ├── silver_21d/
│   └── silver_34d/
│
└── processing_metadata/
    ├── consolidation_manifest.parquet
    └── silver_{interval}_checkpoint.json
```

### RDS PostgreSQL

- `raw_ohlcv` — OHLCV time series with watermark tracking
- `symbol_metadata` — Stock symbol reference data

## Directory Structure

```
batch_layer/
├── fetching/
│   ├── lambda_functions/         # Lambda source code
│   │   ├── daily_ohlcv_fetcher.py
│   │   └── daily_meta_fetcher.py
│   └── requirements.txt
│
├── processing/
│   └── batch_jobs/               # AWS Batch job scripts
│       ├── consolidator.py
│       ├── resampler.py
│       └── requirements.txt
│
├── infrastructure/
│   ├── fetching/deployment_packages/
│   │   └── deploy_lambda.sh
│   ├── processing/
│   │   ├── build_batch_container.sh
│   │   ├── deploy_batch_jobs.sh
│   │   └── Dockerfile
│   ├── orchestration/
│   │   ├── deploy_step_functions.sh
│   │   └── state_machine_definition.json
│   └── modules/                  # Terraform modules
│
├── database/
│   ├── schemas/
│   │   └── schema_init.sql
│   └── README.md
│
├── shared/                       # Shared Python modules
│   └── clients/
│
├── archive_scripts/              # Utility scripts (not deployed)
│
└── deploy.sh                     # Master deployment script
```

## Deployment

### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed
- Python 3.11+
- Terraform (for infrastructure-as-code)

### Quick Deploy

```bash
# Deploy entire batch layer
./deploy.sh dev all

# Deploy specific component
./deploy.sh dev fetching
./deploy.sh dev processing
```

### Individual Component Deployment

```bash
# Lambda functions
cd infrastructure/fetching/deployment_packages
./deploy_lambda.sh

# Docker container (Batch jobs)
cd infrastructure/processing
./build_batch_container.sh
./deploy_batch_jobs.sh

# Step Functions orchestration
cd infrastructure/orchestration
./deploy_step_functions.sh
```

## AWS Resources

| Service | Resource Name | Purpose |
|---------|---------------|---------|
| Lambda | `dev-batch-daily-ohlcv-fetcher` | OHLCV data fetching |
| Lambda | `dev-batch-daily-meta-fetcher` | Metadata fetching |
| AWS Batch | `dev-batch-bronze-consolidator` | Bronze layer consolidation |
| AWS Batch | `dev-batch-duckdb-resampler` | Fibonacci resampling |
| Step Functions | `dev-daily-ohlcv-pipeline` | Pipeline orchestration |
| EventBridge | `dev-daily-ohlcv-pipeline-schedule` | Daily trigger (21:00 UTC) |
| ECR | `dev-batch-processor` | Container image repository |
| RDS | `dev-batch-postgres` | PostgreSQL database |
| S3 | `dev-condvest-datalake` | Data lake storage |

## Technologies

- **Compute**: AWS Lambda, AWS Batch (Fargate)
- **Storage**: Amazon S3, Amazon RDS PostgreSQL
- **Orchestration**: AWS Step Functions, EventBridge Scheduler
- **Processing**: DuckDB (SQL analytics), Pandas, PyArrow
- **Infrastructure**: Terraform

## License

Proprietary — Condvest Inc.
