# Tradlyte Web App - Backend Data Pipeline

## Project Overview

This is the **backend data pipeline component** for the **Tradlyte Web App**, a comprehensive trading analytics platform. The pipeline is responsible for ingesting, processing, and serving financial market data to power three core features:

1. **📊 Backtesting Engine** - Historical data storage and retrieval for strategy validation
2. **🤖 Machine Learning Models** - Clean, structured datasets for predictive analytics and pattern recognition
3. **⚡ Real-time Alerts** - Timely price notifications and technical indicator signals

## Architecture

This repository implements **two complementary architectures** designed for different stages of the platform's evolution:

### 1. AWS Lambda Architecture (`aws_lambda_architecture/`) - **Production Focus**

Cloud-native, serverless implementation designed for scalability and real-time processing:

**Three-Layer Design:**
- **Batch Layer**: Historical OHLCV data processing via AWS Lambda + Batch
  - Daily data ingestion from Polygon.io
  - Fibonacci interval resampling (3d, 5d, 8d, 13d, 21d, 34d)
  - S3 Data Lake (Parquet) + RDS PostgreSQL cache (5-year retention)
  
- **Speed Layer**: Real-time stream processing (Planned)
  - Kinesis Data Streams for live market data
  - Flink SQL for windowed aggregations
  - DynamoDB for tick-level storage with TTL
  
- **Serving Layer**: Fast data access for frontend (Planned)
  - API Gateway REST + WebSocket APIs
  - Redis ElastiCache for sub-millisecond queries
  - CloudFront CDN for global distribution

**Key Features:**
- Auto-scaling serverless infrastructure
- 5-year fast-access cache in RDS + full archive in S3
- Symbol-partitioned data lake for efficient backtesting queries
- Checkpointed batch processing for fault tolerance
- EventBridge scheduling for daily updates

### 2. Prefect Medallion Architecture (`prefect_medallion/`) - **Development/Testing**

Traditional Bronze-Silver-Gold pipeline for local development and prototyping:

- **Bronze Layer**: Raw data ingestion to TimescaleDB
- **Silver Layer**: DuckDB-powered resampling and transformations
- **Gold Layer**: Technical indicators and trading signals
- **Orchestration**: Prefect workflows for dependency management
- **Storage**: Local PostgreSQL + DuckDB + Redis

**Purpose:**
- Rapid prototyping of data transformations
- Local testing without AWS costs
- Algorithm development and validation
- Data quality assurance

## Technology Stack

### AWS Lambda Architecture (Production)
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Data Lake** | S3 + Parquet | Source of truth for all historical data |
| **Fast Cache** | RDS PostgreSQL | Last 5 years for frontend queries |
| **Processing** | AWS Lambda + Batch | Serverless compute for data ingestion/resampling |
| **Streaming** | Kinesis + Flink | Real-time market data processing |
| **API Layer** | API Gateway + Lambda | RESTful and WebSocket endpoints |
| **Caching** | ElastiCache Redis | Sub-millisecond response times |
| **Orchestration** | EventBridge + Step Functions | Scheduling and workflow coordination |

### Prefect Medallion (Development)
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Database** | TimescaleDB | Time-series optimized storage |
| **Analytics** | DuckDB | In-memory analytical processing |
| **Cache** | Redis | Fast lookups and session data |
| **Orchestration** | Prefect | Workflow DAGs and dependency management |
| **Deployment** | Docker Compose | Local containerized environment |

## Data Pipeline Features

### Backtesting Support
- **Historical Coverage**: 63+ years of market data (1962-present)
- **Multiple Timeframes**: 1-minute, daily, and Fibonacci intervals (3d-34d)
- **Symbol-Partitioned**: Efficient queries for individual ticker analysis
- **Parquet Format**: Columnar storage for fast analytical queries
- **5-Year Cache**: Recent data in RDS for sub-second frontend responses

### Machine Learning Ready
- **Clean Schema**: Standardized OHLCV format with timestamps
- **Gap Detection**: Automated missing data identification
- **Incremental Updates**: Daily batch processing with deduplication
- **Feature Engineering**: Pre-computed resampled intervals
- **Audit Trail**: Job metadata tracking for data lineage

### Real-Time Alerts (In Development)
- **Stream Processing**: Kinesis for live tick data ingestion
- **Windowed Aggregations**: Flink SQL for indicator calculations
- **SNS Notifications**: Push alerts for price thresholds and signals
- **WebSocket API**: Real-time subscriptions for frontend updates
- **Rate Limiting**: Controlled notification delivery

## Project Status

**Current Phase:** Batch Layer Implementation (95% Complete)

| Component | Status | Notes |
|-----------|--------|-------|
| **Batch Layer** | ✅ 95% | Ready for testing |
| **Speed Layer** | 📋 Designed | Implementation pending |
| **Serving Layer** | 📋 Designed | Implementation pending |

**Recent Milestones:**
- ✅ Fibonacci resampler processed 10.8M records across 6 intervals
- ✅ RDS→S3 migration completed (22.6M records, 5,350 symbols)
- ✅ 5-year retention policy implemented in RDS
- ✅ Lambda fetcher redesigned for dual S3+RDS writes
- ✅ Symbol-partitioned bronze layer established

**Next Steps:**
- Test Lambda fetcher deployment
- Set up EventBridge daily schedules
- Implement Speed Layer (Kinesis + Flink)
- Build Serving Layer APIs

## Integration with Tradlyte Web App

This data pipeline serves as the **foundational backend** for Tradlyte's trading analytics platform:

```
┌─────────────────────────────────────────────────────────┐
│                    Tradlyte Web App                     │
│  (React Frontend + Node.js Backend + Auth + UI/UX)    │
└───────────────────┬─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Data Pipeline (This Repo)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Batch Layer  │  │ Speed Layer  │  │Serving Layer │ │
│  │ (Historical) │  │ (Real-time)  │  │   (APIs)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │   External Sources    │
         │  - Polygon.io API     │
         │  - Market Data Feeds  │
         └──────────────────────┘
```

**Data Flow:**
1. **Ingestion**: Daily/real-time data from Polygon.io → Pipeline
2. **Processing**: Resampling, indicators, signals → S3 + RDS + DynamoDB
3. **Serving**: API Gateway → Redis cache → Frontend
4. **Backtesting**: Frontend queries → RDS (5yr) or S3 (full history)
5. **ML Models**: Training data → S3 Data Lake → Model endpoints
6. **Alerts**: Signal detection → SNS → WebSocket → User notifications

## Documentation

- [AWS Lambda Architecture Guide](aws_lambda_architecture/README.md)
- [Implementation Status & Roadmap](aws_lambda_architecture/IMPLEMENTATION_STATUS.md)
- [Prefect Medallion Guide](prefect_medallion/README.md)
- [Deployment Procedures](docs/deployment.md)
- [API Specifications](docs/api.md)
- [Data Architecture Diagram](docs/data_architecture.mmd)

## Repository Structure

```
data_pipeline/
├── aws_lambda_architecture/     # Production cloud-native implementation
│   ├── batch_layer/             # Daily OHLCV processing
│   │   ├── fetching/            # Lambda functions for data ingestion
│   │   ├── processing/          # AWS Batch resampling jobs
│   │   ├── database/            # RDS schemas and retention policies
│   │   └── infrastructure/      # Terraform + deployment scripts
│   ├── speed_layer/             # Real-time stream processing (planned)
│   ├── serving_layer/           # API Gateway + caching (planned)
│   └── shared/                  # Common utilities and models
├── prefect_medallion/           # Local development implementation
│   ├── fetch/                   # Data ingestion from APIs
│   ├── ingest/                  # Database loading
│   ├── process/                 # Transformations and indicators
│   ├── flows/                   # Prefect workflow definitions
│   └── tools/                   # Client libraries (Polygon, Postgres, Redis)
├── docs/                        # Architecture and API documentation
└── polygon_data/                # Local data cache for testing
```

## Development Philosophy

This project prioritizes:

1. **Scalability First**: Cloud-native design for millions of data points
2. **Cost Efficiency**: Serverless pay-per-use model + intelligent caching
3. **Data Quality**: Deduplication, gap detection, and audit trails
4. **Fault Tolerance**: Checkpointing, retries, and graceful degradation
5. **Developer Experience**: Local testing environment mirrors production

## License & Usage

This is a **private project** developed specifically for the Tradlyte Web App. It is not intended for public distribution or third-party usage.

---

**Maintained by:** Tradlyte Development Team  
**Last Updated:** October 2025  
**Current Focus:** AWS Lambda Architecture Batch Layer Testing
