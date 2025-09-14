# Prefect Medallion Architecture Implementation

## Overview
This directory contains the **Medallion Architecture** implementation using Prefect for workflow orchestration. It follows the **Bronze → Silver → Gold** pattern for data processing with local development capabilities.

## Architecture Components

### 🥉 Bronze Layer (Raw Data)
- **Data Sources**: Polygon.io API, Yahoo Finance (fallback)
- **Storage**: PostgreSQL/TimescaleDB for raw OHLCV data
- **Processing**: Data extraction and initial validation
- **Schedule**: Daily after market close

### 🥈 Silver Layer (Processed Data)
- **Processing**: Data cleaning, resampling, and aggregation
- **Storage**: DuckDB for analytical processing
- **Features**: Multiple timeframe resampling (1m, 3m, 5m, 8m, 13m, 21m, 34m, 55m)
- **Output**: Clean OHLCV data ready for analysis

### 🥇 Gold Layer (Analytics)
- **Processing**: Technical indicators and trading signals
- **Strategies**: Vegas Channel, custom indicators
- **Storage**: Parquet files for fast analytics
- **Output**: Trading signals and performance metrics

## Directory Structure

```
prefect_medallion/
├── flows/                  # Prefect flow definitions
│   ├── make_bronze_pipeline.py    # Bronze layer flow
│   ├── make_silver_pipeline.py    # Silver layer flow
│   └── make_gold_pipeline.py      # Gold layer flow
├── fetch/                  # Data extraction modules
│   ├── batch.py           # Batch data extraction
│   ├── meta.py            # Symbol metadata extraction
│   └── stream.py          # Real-time data streaming
├── ingest/                 # Data ingestion modules
│   ├── batch.py           # Batch data ingestion
│   └── meta.py            # Metadata ingestion
├── process/                # Data processing modules
│   ├── core/              # Core processing logic
│   │   ├── data_loader.py # Data loading utilities
│   │   ├── resampler.py   # Time series resampling
│   │   ├── indicator.py   # Technical indicators
│   │   ├── cache.py       # Caching mechanisms
│   │   └── alert_rules.py # Alert and notification rules
│   ├── strategies/        # Trading strategies
│   │   └── VegasChannel.py # Vegas Channel strategy
│   ├── sql/               # SQL queries and views
│   │   ├── resample_view.sql      # Resampling views
│   │   └── serializability_check.sql # Data validation
│   └── storage/           # Data storage
│       ├── silver/        # Silver layer storage (DuckDB)
│       └── gold/          # Gold layer storage (Parquet)
├── tools/                  # Utility modules
│   ├── polygon_client.py  # Polygon.io API client
│   ├── postgres_client.py # PostgreSQL client
│   ├── redis_client.py    # Redis client
│   ├── kafka_client.py    # Kafka client
│   └── utils.py           # General utilities
├── config/                 # Configuration management
│   ├── settings.yaml      # Application settings
│   └── load_setting.py    # Settings loader
├── database/               # Database schemas and scripts
│   ├── schema.sql         # Database schema definitions
│   ├── example.sql        # Example queries
│   ├── deletion.sql       # Data cleanup scripts
│   └── sql_analysis.sql   # Analysis queries
├── jupyter_notebook/       # Analysis notebooks
│   ├── tools_functionality.ipynb # Tools testing
│   ├── silver_loading.ipynb      # Silver layer analysis
│   ├── gold_loading.ipynb        # Gold layer analysis
│   ├── olap.ipynb               # OLAP queries
│   └── rest_api.ipynb           # API testing
├── commands/               # Utility commands
│   ├── prefect.sh         # Prefect management commands
│   ├── kafka.cmd          # Kafka management
│   ├── commands.sql       # Database commands
│   └── mongdb.java        # MongoDB utilities
└── test/                   # Test modules
    └── debug_save_gold.py  # Gold layer testing
```

## Key Features

### 🔄 Data Processing Pipeline
1. **Bronze Pipeline**: Raw data extraction from multiple sources
2. **Silver Pipeline**: Data cleaning and resampling
3. **Gold Pipeline**: Analytics and signal generation

### ⚡ Real-time Capabilities
- Kafka-based streaming architecture
- Redis caching for fast access
- Real-time signal generation

### 📊 Analytics & Strategies
- **Vegas Channel Strategy**: Trend-following strategy
- **Custom Indicators**: RSI, MACD, Bollinger Bands
- **Multi-timeframe Analysis**: 1m to 55m intervals

### 🛠️ Development Tools
- **Jupyter Notebooks**: Interactive analysis and development
- **Docker Support**: Containerized deployment
- **Configuration Management**: YAML-based settings

## Getting Started

### Prerequisites
- Python 3.8+
- PostgreSQL/TimescaleDB
- Redis (optional)
- Kafka (optional, for streaming)

### Installation
```bash
cd prefect_medallion/

# Create virtual environment
python -m venv .dp
source .dp/bin/activate  # On Windows: .dp\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp ../.env.example ../.env
# Edit .env with your credentials
```

### Local Development Setup
```bash
# Start Prefect server
prefect server start --host 127.0.0.1 --port 4200

# In another terminal, run flows
source .dp/bin/activate
python flows/make_bronze_pipeline.py
```

### Configuration
Edit `config/settings.yaml` to customize:
- Data extraction parameters
- Processing intervals
- Storage configurations
- Strategy parameters

## Usage Examples

### Running Individual Flows
```bash
# Bronze layer (data extraction)
python flows/make_bronze_pipeline.py

# Silver layer (data processing)
python flows/make_silver_pipeline.py

# Gold layer (analytics)
python flows/make_gold_pipeline.py
```

### Interactive Analysis
```bash
# Start Jupyter
jupyter notebook

# Open analysis notebooks
# - tools_functionality.ipynb: Test tools and connections
# - silver_loading.ipynb: Analyze processed data
# - gold_loading.ipynb: Review trading signals
```

### Strategy Development
```bash
# Add new strategy to process/strategies/
# Update flows/make_gold_pipeline.py
# Test in jupyter_notebook/gold_loading.ipynb
```

## Monitoring & Debugging

### Prefect UI
- Access: http://localhost:4200
- Monitor flow runs and task status
- View logs and metrics

### Data Validation
```sql
-- Check data completeness
SELECT * FROM process/sql/serializability_check.sql

-- Analyze resampled data
SELECT * FROM process/sql/resample_view.sql
```

### Performance Monitoring
- Check DuckDB query performance
- Monitor PostgreSQL connections
- Redis cache hit rates

## Deployment

### Docker Deployment
```bash
# Build container
docker build -t condvest-medallion .

# Run with docker-compose
docker-compose up -d
```

### Production Considerations
- Database connection pooling
- Redis cluster for high availability
- Kafka cluster for streaming
- Monitoring and alerting setup

## Troubleshooting

### Common Issues
1. **Prefect Server Connection**: Ensure server is running on port 4200
2. **Database Connection**: Check PostgreSQL credentials in .env
3. **API Rate Limits**: Polygon.io has rate limits, use delays
4. **Memory Usage**: DuckDB processing can be memory-intensive

### Debug Tools
- Use `test/debug_save_gold.py` for testing gold layer
- Check `jupyter_notebook/tools_functionality.ipynb` for API testing
- Review Prefect logs in the UI

## Performance Optimization

### Data Processing
- Batch processing for efficiency
- Parallel processing where possible
- Optimized SQL queries

### Storage
- TimescaleDB for time-series data
- DuckDB for analytical workloads
- Parquet for compressed analytics storage

## Contributing

1. Follow the medallion architecture pattern
2. Add tests for new features
3. Update configuration documentation
4. Test with realistic data volumes

## Architecture Benefits

### Pros
- **Familiar Pattern**: Traditional ETL approach
- **Local Development**: Full local testing capability
- **Flexible**: Easy to modify and extend
- **Cost Effective**: No cloud costs for development

### Cons
- **Manual Scaling**: Requires infrastructure management
- **Higher Latency**: Batch-oriented processing
- **Maintenance**: More operational overhead than serverless

## Integration with AWS Lambda Architecture

This implementation serves as:
- **Development Environment**: Test strategies locally
- **Backup Processing**: Alternative to cloud processing
- **Analysis Platform**: Deep dive analytics and research
- **Strategy Development**: Prototype new trading strategies

For production real-time processing, consider the AWS Lambda Architecture implementation in `../aws_lambda_architecture/`.
