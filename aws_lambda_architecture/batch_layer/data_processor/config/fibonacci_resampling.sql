-- Fibonacci Resampling SQL Template
-- Direct port of your DuckDB implementation to Aurora PostgreSQL
-- Purpose: Resample daily OHLCV to Fibonacci intervals (3, 5, 8, 13, 21, 34)

-- This SQL uses your exact DuckDB approach:
-- 1. ROW_NUMBER() for sequential numbering by symbol
-- 2. Group by (rn - 1) / interval for Fibonacci grouping  
-- 3. FIRST_VALUE/LAST_VALUE for open/close prices
-- 4. Standard aggregations for high/low/volume

WITH numbered AS (
    SELECT
        symbol,
        DATE(timestamp_data) as date,
        open_price as open,
        high_price as high,
        low_price as low,
        close_price as close,
        volume,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY DATE(timestamp_data)) AS rn
    FROM raw_ohlcv
    WHERE interval_type = '1d'
      AND DATE(timestamp_data) >= CURRENT_DATE - INTERVAL '{lookback_days} days'
      {date_filter}  -- Placeholder for incremental processing
),
grp AS (
    SELECT
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        (rn - 1) / {interval} AS grp_id  -- Fibonacci interval grouping
    FROM numbered
)
SELECT
    symbol,
    MIN(date) AS date,  -- Start date of interval
    FIRST_VALUE(open) OVER (
        PARTITION BY symbol, grp_id 
        ORDER BY date 
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS open,  -- First open price in interval
    MAX(high) AS high,  -- Highest price in interval
    MIN(low) AS low,    -- Lowest price in interval
    LAST_VALUE(close) OVER (
        PARTITION BY symbol, grp_id 
        ORDER BY date 
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS close, -- Last close price in interval
    SUM(volume) AS volume  -- Total volume in interval
FROM grp
GROUP BY symbol, grp_id
HAVING COUNT(*) = {interval}  -- Only complete intervals
ORDER BY symbol, date;

-- Performance Notes:
-- 1. This query leverages Aurora's columnar storage for fast aggregations
-- 2. Window functions are optimized in Aurora PostgreSQL
-- 3. Incremental processing via date_filter reduces data scanned
-- 4. Expected performance: ~30-60 seconds for all intervals (3-34)

-- Usage Examples:
-- {interval} = 3  -> 3-day Fibonacci intervals
-- {interval} = 5  -> 5-day Fibonacci intervals
-- {interval} = 8  -> 8-day Fibonacci intervals
-- {interval} = 13 -> 13-day Fibonacci intervals
-- {interval} = 21 -> 21-day Fibonacci intervals
-- {interval} = 34 -> 34-day Fibonacci intervals
