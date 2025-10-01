# Database Initialization

This directory contains SQL schemas and migration scripts for the batch layer database.

## 📁 Directory Structure

```
database/
├── schemas/              # SQL schema files
│   ├── schema_init_postgres.sql          # Main schema (standard PostgreSQL)
│   ├── timescale_schema_init_postgres.sql # TimescaleDB version (not used in AWS)
│   └── sample_data.sql                   # Sample data for testing
├── migrations/           # Database migration scripts
└── terraform/            # Empty (db_init Lambda removed)
```

## 🚀 Quick Start: Creating Tables

### Method 1: Using psql (Recommended)

```bash
# Get the database password from AWS Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id arn:aws:secretsmanager:ca-west-1:471112909340:secret:dev-batch-postgres-credentials-IWxGJx \
  --region ca-west-1 \
  --query SecretString --output text | jq -r '.password'

# Run the schema initialization script
PGPASSWORD='<password-from-above>' psql \
  -h dev-batch-postgres.czxi9iwguczt.ca-west-1.rds.amazonaws.com \
  -U postgres \
  -d condvest \
  -f schemas/schema_init_postgres.sql
```

### Method 2: Using pgAdmin GUI

1. Connect to RDS:
   - Host: `dev-batch-postgres.czxi9iwguczt.ca-west-1.rds.amazonaws.com`
   - Port: `5432`
   - Database: `condvest`
   - Username: `postgres`
   - Password: (from Secrets Manager)

2. Open SQL Query Tool
3. Copy/paste contents of `schemas/schema_init_postgres.sql`
4. Execute

## 📊 Database Schema

The schema creates the following tables:

### Core Tables

1. **`symbol_metadata`** - Stock symbol information
   - Columns: symbol, name, market, locale, active, primary_exchange, type, marketCap, sector, industry
   - Indexes: symbol (PK), market, type, active

2. **`raw_ohlcv`** - Daily OHLCV price data
   - Columns: symbol, open, high, low, close, volume, timestamp, interval
   - Primary Key: (symbol, timestamp, interval)
   - Indexes: symbol, timestamp, symbol+timestamp, interval

### Silver Layer Tables (Fibonacci Resampled)

3. **`silver_3d`** - 3-day resampled data
4. **`silver_5d`** - 5-day resampled data
5. **`silver_8d`** - 8-day resampled data
6. **`silver_13d`** - 13-day resampled data
7. **`silver_21d`** - 21-day resampled data
8. **`silver_34d`** - 34-day resampled data

Each silver table has:
- Primary Key: (symbol, date)
- Indexes: date, symbol+date

## ✅ Verify Tables Were Created

```bash
# List all tables
PGPASSWORD='<password>' psql \
  -h dev-batch-postgres.czxi9iwguczt.ca-west-1.rds.amazonaws.com \
  -U postgres \
  -d condvest \
  -c "\dt"

# Expected output: 8 tables
# - raw_ohlcv
# - symbol_metadata
# - silver_3d, silver_5d, silver_8d
# - silver_13d, silver_21d, silver_34d
```

## 🔄 Re-initializing the Database

To drop all tables and recreate them:

```sql
-- Drop all tables (be careful!)
DROP TABLE IF EXISTS raw_ohlcv CASCADE;
DROP TABLE IF EXISTS symbol_metadata CASCADE;
DROP TABLE IF EXISTS silver_3d CASCADE;
DROP TABLE IF EXISTS silver_5d CASCADE;
DROP TABLE IF EXISTS silver_8d CASCADE;
DROP TABLE IF EXISTS silver_13d CASCADE;
DROP TABLE IF EXISTS silver_21d CASCADE;
DROP TABLE IF EXISTS silver_34d CASCADE;

-- Then run schema_init_postgres.sql again
```

## 📝 Notes

- **No Lambda Required**: Tables are created manually via SQL scripts, not through Lambda functions
- **Idempotent**: The schema script uses `CREATE TABLE IF NOT EXISTS`, so it's safe to run multiple times
- **Performance**: Includes optimized indexes for time-series queries
- **Standard PostgreSQL**: Uses standard PostgreSQL (not TimescaleDB) for AWS RDS compatibility


