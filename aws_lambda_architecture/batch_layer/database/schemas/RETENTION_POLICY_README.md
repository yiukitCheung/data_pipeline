# 📋 Data Retention Policy Documentation

## 🎯 Overview

This retention policy keeps only the **last 3 years + 1 month** of raw OHLCV data in the `raw_ohlcv` table for fast querying. Older data is automatically archived to `raw_ohlcv_archive` table and removed from the main table.

## 📊 Architecture

```
┌─────────────────────────────────────────────────────┐
│ DATA LIFECYCLE                                       │
└─────────────────────────────────────────────────────┘

1. Fresh Data (0-3 years 1 month)
   └─> Stored in: raw_ohlcv (fast queries)
   
2. Archive Data (>3 years 1 month)
   └─> Moved to: raw_ohlcv_archive (cold storage)
   └─> Deleted from: raw_ohlcv
   
3. Audit Trail
   └─> Logged in: data_retention_log
```

## 🗄️ Database Objects Created

### Tables

1. **`raw_ohlcv_archive`** - Archive table for old OHLCV data
   - Identical structure to `raw_ohlcv`
   - Additional column: `archived_at` (timestamp when archived)
   - Hypertable with 30-day chunks (larger than main table)
   - Aggressive compression enabled (compress after 1 day)

2. **`data_retention_log`** - Audit log for retention operations
   - Tracks each archival job execution
   - Records: date, records archived/deleted, status, errors, execution time

### Stored Procedure

**`archive_old_ohlcv_data()`** - Main archival procedure
- Runs the 3-step archival process:
  1. Copy old data to archive table
  2. Delete old data from main table
  3. Log results

### Views

1. **`v_raw_ohlcv_data_distribution`** - Monthly data distribution in `raw_ohlcv`
2. **`v_archive_statistics`** - Statistics about archived data
3. **`v_retention_log_summary`** - Last 20 retention job executions

## 🚀 Deployment

### Prerequisites

- PostgreSQL client (`psql`) installed
- Access to TimescaleDB instance (local or RDS)
- Appropriate database credentials

### Deploy to Local TimescaleDB

```bash
# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=condvest
export DB_USER=postgres
export DB_PASSWORD=your_password

# Deploy
cd aws_lambda_architecture/batch_layer/database/schemas
./deploy_retention_policy.sh local
```

### Deploy to AWS RDS

```bash
# Set environment variables
export RDS_ENDPOINT=your-rds-endpoint.rds.amazonaws.com
export RDS_USERNAME=postgres
export RDS_PASSWORD=your_password
export RDS_DB_NAME=condvest

# Deploy
./deploy_retention_policy.sh rds
```

### Dry Run (Check What Will Be Archived)

```bash
./deploy_retention_policy.sh dry-run
```

This will show:
- How many records will be archived
- Date range of records to be archived
- Number of unique symbols affected

### Test Deployment

```bash
# Deploy and run a test archival
./deploy_retention_policy.sh test
```

## 📅 Scheduling

### Option 1: AWS Lambda (Recommended for RDS)

Create a Lambda function that runs weekly:

```python
import psycopg2

def lambda_handler(event, context):
    conn = psycopg2.connect(
        host=os.environ['RDS_ENDPOINT'],
        database=os.environ['RDS_DB_NAME'],
        user=os.environ['RDS_USERNAME'],
        password=os.environ['RDS_PASSWORD']
    )
    
    with conn.cursor() as cur:
        cur.execute("CALL archive_old_ohlcv_data();")
        conn.commit()
    
    conn.close()
    return {'statusCode': 200, 'body': 'Archival completed'}
```

Schedule with EventBridge: Every Sunday at 2 AM UTC
```
cron(0 2 ? * SUN *)
```

### Option 2: pg_cron (If enabled on RDS)

```sql
-- Schedule weekly archival (every Sunday at 2 AM)
SELECT cron.schedule(
    'weekly-ohlcv-archival',
    '0 2 * * 0',
    'CALL archive_old_ohlcv_data();'
);
```

### Option 3: Local Cron Job

```bash
# Add to crontab
0 2 * * 0 /path/to/run_archival.sh >> /var/log/archival.log 2>&1
```

## 🔍 Monitoring & Queries

### Check Current Data Distribution

```sql
SELECT * FROM v_raw_ohlcv_data_distribution;
```

Output:
```
month        | record_count | unique_symbols | earliest_timestamp | latest_timestamp
-------------+--------------+----------------+--------------------+-----------------
2025-10-01  | 150000       | 5350           | 2025-10-01         | 2025-10-18
2025-09-01  | 450000       | 5350           | 2025-09-01         | 2025-09-30
...
```

### Check Archive Statistics

```sql
SELECT * FROM v_archive_statistics;
```

Output:
```
total_archived_records | unique_symbols | earliest_timestamp | latest_timestamp | table_size
-----------------------+----------------+--------------------+------------------+-----------
10000000               | 5350           | 1962-01-01         | 2021-08-31       | 2.5 GB
```

### Check Recent Archival Jobs

```sql
SELECT * FROM v_retention_log_summary;
```

Output:
```
execution_date      | records_archived | records_deleted | status  | consistency_check
--------------------+------------------+-----------------+---------+------------------
2025-10-13 02:00:01 | 150000          | 150000          | success | ✅ Consistent
2025-10-06 02:00:01 | 148000          | 148000          | success | ✅ Consistent
```

### Manual Dry Run (Before Actual Archival)

```sql
-- Check what will be archived
SELECT 
    COUNT(*) AS records_to_archive,
    MIN(timestamp) AS oldest_record,
    MAX(timestamp) AS newest_record_to_archive,
    COUNT(DISTINCT symbol) AS unique_symbols
FROM raw_ohlcv
WHERE timestamp < CURRENT_DATE - INTERVAL '3 years 1 month';
```

### Check Storage Sizes

```sql
SELECT 
    'raw_ohlcv' AS table_name,
    pg_size_pretty(pg_total_relation_size('raw_ohlcv')) AS size
UNION ALL
SELECT 
    'raw_ohlcv_archive' AS table_name,
    pg_size_pretty(pg_total_relation_size('raw_ohlcv_archive')) AS size;
```

## 🔧 Manual Execution

### Run Archival Manually

```sql
CALL archive_old_ohlcv_data();
```

### Query Archive Data

```sql
-- Get data from archive
SELECT * FROM raw_ohlcv_archive
WHERE symbol = 'AAPL'
  AND timestamp BETWEEN '2020-01-01' AND '2020-12-31'
ORDER BY timestamp;
```

### Restore Archived Data (If Needed)

```sql
-- Move data back from archive to main table
INSERT INTO raw_ohlcv (symbol, open, high, low, close, volume, timestamp, interval)
SELECT symbol, open, high, low, close, volume, timestamp, interval
FROM raw_ohlcv_archive
WHERE timestamp BETWEEN '2020-01-01' AND '2020-12-31'
ON CONFLICT (symbol, timestamp, interval) DO NOTHING;
```

## ⚠️ Important Notes

### Data Consistency

The procedure ensures **data consistency**:
1. Data is copied to archive **FIRST**
2. Only then is data deleted from main table
3. If archival fails, deletion is skipped
4. All operations are logged

### Performance Considerations

- Archival runs in a single transaction (ACID compliant)
- May take several minutes for large datasets
- Recommend running during low-traffic periods (e.g., Sunday 2 AM)
- Compression reduces storage costs significantly

### Retention Threshold

Current: **3 years + 1 month buffer**

To change:
```sql
-- Edit retention_policy.sql line:
v_retention_threshold := CURRENT_DATE - INTERVAL '3 years 1 month';

-- Example: Change to 2 years + 1 month
v_retention_threshold := CURRENT_DATE - INTERVAL '2 years 1 month';
```

### Storage Costs

**Before retention policy:**
- `raw_ohlcv`: ~15-20 GB (60+ years of data)
- RDS storage: ~$100-150/month

**After retention policy:**
- `raw_ohlcv`: ~3-4 GB (3 years of data)
- `raw_ohlcv_archive`: ~12-16 GB (compressed, cold storage)
- RDS storage: ~$30-50/month
- **Savings: ~60-70%**

## 🐛 Troubleshooting

### Error: "relation does not exist"

The tables haven't been created yet. Run deployment:
```bash
./deploy_retention_policy.sh local
```

### Error: "could not serialize access due to concurrent update"

Another archival job is running. Wait for it to complete.

### Records Archived ≠ Records Deleted

Check `data_retention_log` for details:
```sql
SELECT * FROM data_retention_log 
WHERE status != 'success' 
ORDER BY execution_date DESC;
```

### Archive Table Growing Too Large

Consider setting up a secondary archival to S3:
1. Export old archive data to S3 Parquet files
2. Delete from `raw_ohlcv_archive` (keep last 10 years)
3. Use Athena to query S3 for very old data

## 📚 Next Steps

1. ✅ Deploy retention policy to local TimescaleDB
2. ✅ Test with dry-run
3. ✅ Run manual test archival
4. 🔄 Set up weekly Lambda schedule
5. 🔄 Monitor first few runs
6. 🔄 Adjust retention threshold if needed
7. 🔄 Deploy to production RDS

## 🔗 Related Files

- `retention_policy.sql` - Main SQL script
- `deploy_retention_policy.sh` - Deployment script
- `timescale_schema_init_postgres.sql` - Main schema
- `daily_ohlcv_fetcher.py` - Lambda that writes to `raw_ohlcv`

## 📝 Change Log

- **2025-10-18**: Initial retention policy created
  - 3 years + 1 month retention
  - Archive table with compression
  - Audit logging
  - Monitoring views

