# Batch Layer Validation Checklist

## Current Status: VALIDATING PHASE 1

**Date:** October 18, 2025  
**Batch Job:** `full-resampling-test-20251018-102108` - RUNNING

---

## 🔍 Issues Identified

### 1. RDS Data Lifecycle - CRITICAL ⚠️

**Problem:** Lambda fetcher stores ALL historical data in RDS
- No archival strategy
- RDS will grow indefinitely
- Expensive storage for old data

**Current Situation:**
- S3 has 22.6M records (1962-2025) via AWS DMS migration
- RDS also has all this data?
- No automatic archival process

**Solution Needed:**
```
Strategy: Keep only last 2 years in RDS for fast frontend queries
- RDS: Recent data (2023-2025) → Fast queries
- S3: All historical data (1962-2025) → Cost-effective storage
- Automatic archival: Move data >2 years old to S3
```

### 2. Lambda Fetcher Issues

**File:** `batch_layer/fetching/lambda_functions/daily_ohlcv_fetcher.py`

**Issues:**
- Line 132: Stores directly to RDS, no S3 write
- Line 207: References `bronze_ohlcv` table (should be `raw_ohlcv`?)
- No logic to archive old data
- Triggers resampler for every fetch (line 157) - may be inefficient

### 3. Resampler S3 Path

**File:** `batch_layer/processing/batch_jobs/resampler.py`

**Questions:**
- Does it read from S3 `public/raw_ohlcv/` or RDS?
- Should it write processed data back to RDS or just S3?
- What's the data flow?

---

## ✅ Validation Steps

### Step 1: Check Current Batch Job Status
- [ ] Verify all 6 intervals complete successfully
- [ ] Check CloudWatch logs for errors
- [ ] Confirm total records processed

### Step 2: Verify Checkpoint Files
```bash
aws s3 ls s3://dev-condvest-datalake/processing_metadata/ --region ca-west-1
```
Expected files:
- [ ] silver_3d_checkpoint.json
- [ ] silver_5d_checkpoint.json
- [ ] silver_8d_checkpoint.json
- [ ] silver_13d_checkpoint.json
- [ ] silver_21d_checkpoint.json
- [ ] silver_34d_checkpoint.json

### Step 3: Validate S3 Data Lake Structure
```bash
# Check silver layer outputs
aws s3 ls s3://dev-condvest-datalake/silver/ --recursive --human-readable --summarize

# Check partitioning structure
aws s3 ls s3://dev-condvest-datalake/silver/silver_3d/ --recursive | head -20
```
Expected structure:
```
silver/
├── silver_3d/
│   ├── year=2012/month=08/data_3d_201208.parquet
│   ├── year=2012/month=09/data_3d_201209.parquet
│   └── ...
├── silver_5d/
│   └── year=YYYY/month=MM/data_5d_YYYYMM.parquet
└── ... (for all 6 intervals)
```

### Step 4: Check RDS Data Volume
```sql
-- Connect to RDS and check:
SELECT 
  COUNT(*) as total_records,
  MIN(DATE(timestamp)) as earliest_date,
  MAX(DATE(timestamp)) as latest_date,
  COUNT(DISTINCT symbol) as unique_symbols
FROM raw_ohlcv;
```

**Question:** Do we have 63 years of data in RDS too? (Expensive!)

### Step 5: Validate Data Consistency
- [ ] Compare record counts: S3 bronze vs RDS
- [ ] Verify resampled data quality
- [ ] Check for duplicate records
- [ ] Validate date ranges

---

## 🔧 Fixes Needed

### Fix 1: Implement RDS Archival Strategy

**Create archival Lambda:**
```python
# archive_old_data_lambda.py
# Purpose: Archive RDS data >2 years old to S3

def lambda_handler(event, context):
    # 1. Export data >2 years old from RDS to S3
    # 2. Verify export success
    # 3. Delete archived data from RDS
    # 4. Update metadata table
```

**Schedule:** Run monthly via EventBridge

### Fix 2: Update Lambda Fetcher

**Changes needed in `daily_ohlcv_fetcher.py`:**
1. Write to both RDS AND S3 bronze layer
2. Fix table name reference (`bronze_ohlcv` vs `raw_ohlcv`)
3. Only trigger resampler once per day (not per batch)

### Fix 3: Clarify Data Flow

**Proposed Architecture:**
```
Daily Lambda → RDS (recent 2 years) + S3 bronze (all data)
             ↓
    AWS Batch Resampler → Read from S3 bronze
                        → Write to S3 silver
                        → Optionally write to RDS silver tables
```

---

## 📝 Action Items (In Order)

1. **WAIT** for batch job to complete
2. **VALIDATE** checkpoint files and S3 structure
3. **CHECK** what's in RDS currently
4. **DECIDE** data flow strategy:
   - Option A: RDS for recent data only, S3 for everything
   - Option B: S3 only, no RDS (pure data lake)
   - Option C: Hybrid (current mess)
5. **IMPLEMENT** archival strategy
6. **FIX** Lambda fetcher code
7. **TEST** incremental processing
8. **SETUP** EventBridge schedule

---

## 🤔 Questions for User

1. **What's currently in RDS?**
   - All 63 years of data?
   - Or just recent data?
   - Check: `SELECT COUNT(*) FROM raw_ohlcv;`

2. **What's the data flow you want?**
   - Lambda → RDS + S3?
   - Lambda → S3 only?
   - Archive RDS → S3 monthly?

3. **Do you need resampled data in RDS?**
   - For frontend fast queries?
   - Or can frontend query S3 via Athena?

---

## 📊 Current Understanding

**S3 (confirmed):**
- Bronze: 22.6M records (1962-2025)
- Silver: Being processed now (4.5M+ per interval)
- Checkpoints: New system working

**RDS (unknown):**
- Volume?
- Date range?
- Need to check!

**Lambda Fetcher:**
- Fetches daily data from Polygon
- Stores to RDS
- NO S3 write currently
- NO archival logic

**Resampler:**
- Reads from S3 bronze
- Writes to S3 silver
- Creates checkpoints
- Working well!

---

**Next:** Wait for batch job, then validate everything step-by-step.

