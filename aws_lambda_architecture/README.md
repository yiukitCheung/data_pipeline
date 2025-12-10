# AWS Lambda Architecture Implementation

## Overview

This directory contains the AWS-native implementation of the Condvest data pipeline using **Lambda Architecture** pattern for real-time financial data processing.

## 🏗️ Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           CONDVEST DATA PIPELINE                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         DATA SOURCES                                     │   │
│   │  ┌──────────────┐                         ┌──────────────┐              │   │
│   │  │ Polygon REST │  Daily OHLCV            │ Polygon WS   │  Real-time   │   │
│   │  └──────┬───────┘                         └──────┬───────┘              │   │
│   └─────────┼────────────────────────────────────────┼──────────────────────┘   │
│             │                                        │                          │
│   ┌─────────▼────────────────────────┐   ┌──────────▼────────────────────┐     │
│   │     BATCH LAYER (✅ 100%)         │   │     SPEED LAYER (⚠️ 50%)      │     │
│   │                                  │   │                               │     │
│   │  ┌────────────────────────────┐  │   │  ECS Fargate → Kinesis        │     │
│   │  │   Step Functions Pipeline  │  │   │         ↓                     │     │
│   │  │  ┌────────┐ ┌────────┐    │  │   │  Kinesis Analytics (Flink)    │     │
│   │  │  │Fetchers│→│Consol. │    │  │   │         ↓                     │     │
│   │  │  │(Lambda)│ │(Batch) │    │  │   │  DynamoDB (tick storage)      │     │
│   │  │  └────────┘ └───┬────┘    │  │   │                               │     │
│   │  │       ┌─────────▼──────┐  │  │   │                               │     │
│   │  │       │Resamplers (6x) │  │  │   │                               │     │
│   │  │       │  (Parallel)    │  │  │   │                               │     │
│   │  │       └────────────────┘  │  │   │                               │     │
│   │  └────────────────────────────┘  │   │                               │     │
│   └──────────────────────────────────┘   └───────────────────────────────┘     │
│                        │                              │                         │
│                        └──────────────┬───────────────┘                         │
│                                       │                                         │
│   ┌───────────────────────────────────▼──────────────────────────────────────┐  │
│   │                       SERVING LAYER (⚠️ 30%)                              │  │
│   │                                                                          │  │
│   │     ┌─────────┐     ┌─────────────┐     ┌──────────────┐                │  │
│   │     │  Redis  │ ←── │ API Gateway │ ←── │  CloudFront  │ ←── Users     │  │
│   │     │ (cache) │     │  (REST/WS)  │     │    (CDN)     │                │  │
│   │     └─────────┘     └─────────────┘     └──────────────┘                │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Structure

```
aws_lambda_architecture/
├── batch_layer/                 # ✅ Daily batch processing (100% complete)
│   ├── database/               # Database schemas
│   ├── fetching/               # Lambda functions
│   │   └── lambda_functions/
│   │       ├── daily_ohlcv_fetcher.py
│   │       └── daily_meta_fetcher.py
│   ├── processing/             # AWS Batch jobs
│   │   └── batch_jobs/
│   │       ├── consolidator.py     # Merge date files
│   │       ├── resampler.py        # Fibonacci resampling
│   │       └── vaccume.py          # Cleanup old files (local)
│   ├── infrastructure/         # Deployment & orchestration
│   │   ├── fetching/           # Lambda deployment scripts
│   │   ├── processing/         # Batch container & job deployment
│   │   └── orchestration/      # Step Functions pipeline
│   │       ├── state_machine_definition.json
│   │       └── deploy_step_functions.sh
│   ├── shared/                 # Shared utilities
│   └── BATCH_LAYER_IMPLEMENTATION_SUMMARY.md
│
├── speed_layer/                 # ⚠️ Real-time processing (50% complete)
│   ├── data_fetcher/           # ECS WebSocket service
│   ├── kinesis_analytics/      # Flink SQL queries
│   └── README.md
│
├── serving_layer/               # ⚠️ API serving (30% complete)
│   ├── api_gateway/            # API configurations
│   └── lambda_functions/       # API backends
│
├── shared/                      # Common utilities
│   ├── clients/                # AWS service clients
│   ├── models/                 # Data models
│   └── utils/                  # Utility functions
│
└── README.md                    # This file
```

---

## ✅ Implementation Status

### Batch Layer (100% Complete) 🎉

| Component | Status | Description |
|-----------|--------|-------------|
| **Lambda OHLCV Fetcher** | ✅ Deployed | Daily data ingestion from Polygon |
| **Lambda Meta Fetcher** | ✅ Deployed | Symbol metadata updates |
| **Watermark System** | ✅ Working | Incremental processing tracking |
| **S3 Bronze Layer** | ✅ Working | Raw data storage (symbol partitioned) |
| **Consolidation Job** | ✅ Deployed | AWS Batch: Merge date files → data.parquet |
| **Vacuum/Cleanup** | ✅ Integrated | Consolidator cleans up old files |
| **Resampler** | ✅ Deployed | AWS Batch: Fibonacci resampling (3d-34d) |
| **Checkpoint System** | ✅ Working | Incremental resampling |
| **S3 Silver Layer** | ✅ Validated | Resampled data storage |
| **Step Functions** | ✅ Deployed | Pipeline orchestration with parallel execution |
| **SNS Alerts** | ✅ Configured | Failure notifications |

### Speed Layer (50% Complete)

| Component | Status | Description |
|-----------|--------|-------------|
| **ECS WebSocket Service** | ✅ Code Ready | Polygon WebSocket connection |
| **Kinesis Streams** | ⚠️ Not Deployed | Real-time data ingestion |
| **Kinesis Analytics** | ⚠️ Not Deployed | Stream processing (Flink SQL) |
| **DynamoDB** | ⚠️ Not Deployed | Tick storage with TTL |
| **Signal Generation** | ❌ Not Started | Price alerts, indicators |

### Serving Layer (30% Complete)

| Component | Status | Description |
|-----------|--------|-------------|
| **API Gateway** | ⚠️ Not Deployed | REST API endpoints |
| **WebSocket API** | ❌ Not Started | Real-time subscriptions |
| **Redis Cache** | ⚠️ Not Deployed | Latest prices cache |
| **CloudFront** | ❌ Not Started | CDN distribution |

---

## 🚀 Quick Start

### Batch Layer (Local Testing)

```bash
# Activate virtual environment
cd data_pipeline
source .dp/bin/activate

# Run consolidation locally
cd aws_lambda_architecture/batch_layer/processing/batch_jobs
python consolidator.py --mode incremental --max-workers 10

# Run vacuum (dry-run)
python vaccume.py --dry-run

# Run resampler locally
python resampler.py
```

### Manual Pipeline Trigger (AWS)

```bash
# Trigger the entire Step Functions pipeline
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:ca-west-1:471112909340:stateMachine:condvest-daily-ohlcv-pipeline" \
  --name "manual-$(date +%Y%m%d%H%M%S)" \
  --region ca-west-1

# Or trigger individual Batch jobs
aws batch submit-job \
  --job-name manual-consolidator-$(date +%Y%m%d%H%M%S) \
  --job-queue dev-batch-duckdb-resampler \
  --job-definition dev-batch-bronze-consolidator \
  --region ca-west-1
```

### Deploy Lambda Functions

```bash
cd aws_lambda_architecture/batch_layer/infrastructure/fetching/deployment_packages
./deploy_lambda.sh daily-ohlcv-fetcher
```

---

## 📊 Data Pipeline Summary

### Daily Flow (Fully Automated via Step Functions)

```
Market Close (4:00 PM ET)
         │
         ▼ 4:05 PM ET (21:05 UTC)
   EventBridge → Step Functions Pipeline
         │
         ▼ STAGE 1 (Parallel)
   ┌─────────────┬──────────────────┐
   │ OHLCV Fetch │  Metadata Fetch  │  ← Lambda (2 retries each)
   └─────────────┴──────────────────┘
         │
         ▼ STAGE 2 (Sequential)
   ┌────────────────────────────────┐
   │ Consolidator (AWS Batch)       │  ← Merges date files + cleanup
   └────────────────────────────────┘
         │
         ▼ STAGE 3 (Parallel - 6x)
   ┌────┬────┬────┬─────┬─────┬─────┐
   │ 3d │ 5d │ 8d │ 13d │ 21d │ 34d │  ← All resamplers in parallel!
   └────┴────┴────┴─────┴─────┴─────┘
         │
         ▼ ~4:23 PM ET
   ✅ Pipeline Complete (~18 min total)

   ON FAILURE → SNS Alert → Email notification
```

### Monthly Flow (Maintenance)
```
Vacuum Script (local) → Deep clean old date files if needed
```

---

## 💰 Estimated Monthly Costs (MVP)

| Service | Cost |
|---------|------|
| Lambda (fetchers) | $5 |
| RDS (t3.micro) | $20 |
| S3 Storage | $10 |
| AWS Batch | $15 |
| Step Functions | $2 |
| SNS Alerts | $1 |
| **Batch Layer Total** | **$53** |
| | |
| Kinesis Streams | $50 |
| Kinesis Analytics | $50 |
| DynamoDB | $15 |
| **Speed Layer Total** | **$115** |
| | |
| API Gateway | $10 |
| ElastiCache | $15 |
| CloudFront | $10 |
| **Serving Layer Total** | **$35** |
| | |
| **TOTAL** | **~$200/month** |

---

## 📚 Documentation

- [**Batch Layer Summary**](./batch_layer/BATCH_LAYER_IMPLEMENTATION_SUMMARY.md) - Full implementation details
- [**Orchestration README**](./batch_layer/infrastructure/orchestration/README.md) - Step Functions pipeline
- [**Speed Layer README**](./speed_layer/README.md) - Real-time processing docs

---

## 🎯 Key Benefits

1. **Serverless-First**: Pay only for what you use
2. **Auto-Scaling**: Handle traffic spikes automatically
3. **Managed Services**: Minimal operational overhead
4. **Incremental Processing**: Smart data compaction
5. **Cost-Optimized**: ~$200/month for full stack
6. **Industry Standards**: Delta Lake/Iceberg-style patterns
7. **Orchestrated Pipeline**: Step Functions for reliability & visibility
8. **Parallel Execution**: ~3x faster with parallel resamplers
9. **Failure Alerts**: SNS notifications on pipeline failures

---

**Last Updated:** December 10, 2025  
**Overall Status:** ✅ Batch Layer 100% Complete & Automated | Speed/Serving Layers In Progress
