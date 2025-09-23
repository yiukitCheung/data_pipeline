# Batch Layer - Local Development

## 🎯 Purpose

Local development environment for testing the batch layer independently:
- **Daily OHLCV Fetcher** (Lambda simulation)
- **Fibonacci Resampler** (AWS Batch simulation)
- **TimescaleDB** (Aurora simulation)

## 🏗️ Architecture

```mermaid
graph TD
    A["💻 Local Development"] --> B["🐳 Docker Compose"]
    B --> C["📊 TimescaleDB<br/>Port 5433"]
    B --> D["⚡ Lambda Simulator<br/>daily_ohlcv_fetcher"]
    B --> E["🚀 Batch Simulator<br/>fibonacci_resampler"]
    
    F["📊 Polygon API"] --> D
    D --> C
    E --> C
    
    style A fill:#e1f5fe
    style D fill:#f3e5f5
    style E fill:#e8f5e8
    style C fill:#fff3e0
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
cd batch_layer/local_dev

# Copy environment template
cp env.example .env

# Edit .env with your Polygon API key
vim .env  # Add your POLYGON_API_KEY
```

### 2. Start Services

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 3. Test Daily OHLCV Fetcher (Lambda Simulation)

```bash
# Run daily OHLCV fetcher
docker exec -it batch-lambda-simulator python lambda_functions/daily_ohlcv_fetcher.py

# Check data was inserted
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "SELECT COUNT(*) FROM raw_ohlcv;"
```

### 4. Test Fibonacci Resampler (Batch Simulation)

```bash
# Run Fibonacci resampling
docker exec -it batch-fibonacci-simulator python data_processor/resampler.py

# Check resampled data
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "SELECT symbol, date, close FROM silver_3d LIMIT 5;"
```

### 5. Inspect Database

```bash
# Connect to TimescaleDB
docker exec -it batch-timescaledb psql -U condvest_user -d condvest

# Useful queries:
# \dt                          -- List tables
# SELECT * FROM symbol_metadata;
# SELECT symbol, COUNT(*) FROM raw_ohlcv GROUP BY symbol;
# SELECT symbol, COUNT(*) FROM silver_3d GROUP BY symbol;
```

## 📊 Sample Data

The environment comes with sample data:
- **5 symbols**: AAPL, GOOGL, MSFT, TSLA, NVDA
- **45+ trading days** of OHLCV data for AAPL
- **Fewer days** for other symbols (for variety)
- **Fibonacci tables** ready for resampling (3d, 5d, 8d, 13d, 21d, 34d)

## 🧪 Testing Scenarios

### Test Complete Pipeline

```bash
# 1. Fetch fresh data
docker exec -it batch-lambda-simulator python lambda_functions/daily_ohlcv_fetcher.py

# 2. Resample to Fibonacci intervals
docker exec -it batch-fibonacci-simulator python data_processor/resampler.py

# 3. Verify results
docker exec -it batch-timescaledb psql -U condvest_user -d condvest -c "
SELECT 
    'raw' as table_type, symbol, COUNT(*) as records 
FROM raw_ohlcv GROUP BY symbol
UNION ALL
SELECT 
    'silver_3d' as table_type, symbol, COUNT(*) as records 
FROM silver_3d GROUP BY symbol
ORDER BY table_type, symbol;
"
```

### Test Individual Components

```bash
# Test just the resampler with existing data
docker exec -it batch-fibonacci-simulator python data_processor/resampler.py --intervals 3 5

# Test database connection
docker exec -it batch-fibonacci-simulator python -c "from shared.clients.local_postgres_client import LocalPostgresClient; client = LocalPostgresClient('postgresql://condvest_user:condvest_pass@timescaledb:5432/condvest'); print('Connected:', client.get_active_symbols())"
```

## 🔧 Configuration

Key environment variables in `.env`:

```bash
# API Configuration
POLYGON_API_KEY=your_key_here

# Database
DATABASE_URL=postgresql://condvest_user:condvest_pass@localhost:5433/condvest

# Fibonacci Intervals (matching AWS)
FIBONACCI_INTERVALS=3,5,8,13,21,34
LOOKBACK_DAYS=300
```

## 📁 File Structure

```
local_dev/
├── docker-compose.yml      # Multi-service setup
├── Dockerfile.lambda       # Lambda simulator
├── init_sql/              # Database initialization
│   ├── 01_create_tables.sql
│   └── 02_sample_data.sql
├── env.example            # Environment template
└── README.md             # This file
```

## 🛠️ Troubleshooting

### Common Issues

```bash
# Database connection issues
docker-compose logs timescaledb

# Lambda simulator issues
docker-compose logs lambda-simulator

# Batch simulator issues
docker-compose logs batch-simulator

# Reset everything
docker-compose down -v
docker-compose up -d
```

### Port Conflicts

```bash
# If port 5433 is in use, change in docker-compose.yml:
services:
  timescaledb:
    ports:
      - "5434:5432"  # Use different port
```

## 🔄 Development Workflow

1. **Make code changes** in parent directories (`../lambda_functions/`, `../data_processor/`)
2. **Restart containers** to pick up changes: `docker-compose restart`
3. **Test changes** using the commands above
4. **Debug** with logs: `docker-compose logs -f service_name`
5. **Clean slate** when needed: `docker-compose down -v && docker-compose up -d`

## 🎯 Benefits

✅ **Independent Testing** - Test batch layer without other layers
✅ **Fast Iteration** - No AWS deployment needed
✅ **Real Data** - Uses actual Polygon API
✅ **Production-Like** - TimescaleDB matches Aurora features
✅ **Fibonacci Ready** - Test all intervals (3-34)
✅ **Clean Environment** - Easy reset and reproduce issues

---

**🎯 Goal**: Test your Fibonacci resampling logic locally before AWS deployment!
