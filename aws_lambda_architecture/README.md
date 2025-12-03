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
│   │      BATCH LAYER (✅ 95%)         │   │     SPEED LAYER (⚠️ 50%)      │     │
│   │                                  │   │                               │     │
│   │  Lambda Fetcher → S3 Bronze      │   │  ECS Fargate → Kinesis        │     │
│   │         ↓                        │   │         ↓                     │     │
│   │  Consolidator → data.parquet     │   │  Kinesis Analytics (Flink)    │     │
│   │         ↓                        │   │         ↓                     │     │
│   │  Resampler → S3 Silver           │   │  DynamoDB (tick storage)      │     │
│   │         ↓                        │   │                               │     │
│   │  Vacuum → Cleanup old files      │   │                               │     │
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
├── batch_layer/                 # ✅ Daily batch processing (95% complete)
│   ├── database/               # Database schemas
│   ├── fetching/               # Lambda functions
│   │   └── lambda_functions/
│   │       ├── daily_ohlcv_fetcher.py
│   │       └── daily_meta_fetcher.py
│   ├── processing/             # AWS Batch jobs
│   │   └── batch_jobs/
│   │       ├── resampler.py        # Fibonacci resampling
│   │       ├── consolidate.py      # Merge date files
│   │       └── vaccume.py          # Cleanup old files
│   ├── shared/                 # Shared utilities
│   └── README.md
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

### Batch Layer (95% Complete)

| Component | Status | Description |
|-----------|--------|-------------|
| **Lambda OHLCV Fetcher** | ✅ Deployed | Daily data ingestion from Polygon |
| **Lambda Meta Fetcher** | ✅ Deployed | Symbol metadata updates |
| **Watermark System** | ✅ Working | Incremental processing tracking |
| **S3 Bronze Layer** | ✅ Working | Raw data storage (symbol partitioned) |
| **Consolidation Job** | ✅ Implemented | Merge date files → data.parquet |
| **Vacuum Job** | ✅ Implemented | Cleanup old date files |
| **Resampler** | ✅ Validated | Fibonacci resampling (3d-34d) |
| **Checkpoint System** | ✅ Working | Incremental resampling |
| **S3 Silver Layer** | ✅ Validated | Resampled data storage |

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

# Run consolidation
cd aws_lambda_architecture/batch_layer/processing/batch_jobs
python consolidate.py --symbols AAPL,MSFT

# Run vacuum (dry-run)
python vaccume.py --dry-run

# Run resampler
python resampler.py
```

### Deploy Lambda Functions

```bash
cd aws_lambda_architecture/batch_layer/fetching/deployment_packages
./deploy_lambda.sh daily-ohlcv-fetcher
```

---

## 📊 Data Pipeline Summary

### Daily Flow (Automated)
```
4:05 PM ET → Lambda Fetcher → S3 Bronze (date=*.parquet) + RDS
```

### Weekly Flow (Manual/Scheduled)
```
Consolidation → data.parquet → Resampler → S3 Silver
```

### Monthly Flow (Maintenance)
```
Vacuum → Clean old date files → Save storage costs
```

---

## 💰 Estimated Monthly Costs (MVP)

| Service | Cost |
|---------|------|
| Lambda (fetchers) | $5 |
| RDS (t3.micro) | $20 |
| S3 Storage | $10 |
| AWS Batch | $10 |
| **Batch Layer Total** | **$45** |
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

- [**Batch Layer README**](./batch_layer/README.md) - Detailed batch layer docs
- [**Implementation Summary**](./batch_layer/BATCH_LAYER_IMPLEMENTATION_SUMMARY.md) - Full implementation details
- [**Speed Layer README**](./speed_layer/README.md) - Real-time processing docs

---

## 🎯 Key Benefits

1. **Serverless-First**: Pay only for what you use
2. **Auto-Scaling**: Handle traffic spikes automatically
3. **Managed Services**: Minimal operational overhead
4. **Incremental Processing**: Smart data compaction
5. **Cost-Optimized**: ~$200/month for full stack
6. **Industry Standards**: Delta Lake/Iceberg-style patterns

---

**Last Updated:** December 3, 2025  
**Overall Status:** Batch Layer Production-Ready, Speed/Serving Layers In Progress
