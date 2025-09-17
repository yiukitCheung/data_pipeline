-- ===============================================
-- Kinesis Analytics SQL for Real-time OHLCV Generation
-- ===============================================

-- Create input stream from Kinesis Data Streams
CREATE OR REPLACE STREAM "SOURCE_SQL_STREAM_001" (
    symbol VARCHAR(10),
    price DECIMAL(10,2),
    volume BIGINT,
    timestamp TIMESTAMP,
    exchange VARCHAR(10),
    conditions VARCHAR(100)
);

-- ===============================================
-- 1-Minute OHLCV Aggregation
-- ===============================================

CREATE OR REPLACE STREAM "ohlcv_1min_stream" AS
SELECT 
    symbol,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as window_start,
    DATEADD(MINUTE, 1, ROWTIME_TO_TIMESTAMP(ROWTIME)) as window_end,
    
    -- OHLCV calculations
    (ARRAY_AGG(price ORDER BY timestamp ASC))[1] as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    (ARRAY_AGG(price ORDER BY timestamp DESC))[1] as close_price,
    SUM(volume) as total_volume,
    COUNT(*) as tick_count,
    
    -- Metadata
    'LIVE' as data_source,
    '1m' as interval_type
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL 
  AND price > 0 
  AND volume > 0
GROUP BY 
    symbol,
    ROWTIME_RANGE INTERVAL '1' MINUTE;

-- ===============================================
-- 5-Minute OHLCV Aggregation
-- ===============================================

CREATE OR REPLACE STREAM "ohlcv_5min_stream" AS
SELECT 
    symbol,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as window_start,
    DATEADD(MINUTE, 5, ROWTIME_TO_TIMESTAMP(ROWTIME)) as window_end,
    
    -- OHLCV calculations
    (ARRAY_AGG(price ORDER BY timestamp ASC))[1] as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    (ARRAY_AGG(price ORDER BY timestamp DESC))[1] as close_price,
    SUM(volume) as total_volume,
    COUNT(*) as tick_count,
    
    -- Metadata
    'LIVE' as data_source,
    '5m' as interval_type
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL 
  AND price > 0 
  AND volume > 0
GROUP BY 
    symbol,
    ROWTIME_RANGE INTERVAL '5' MINUTE;

-- ===============================================
-- 15-Minute OHLCV Aggregation
-- ===============================================

CREATE OR REPLACE STREAM "ohlcv_15min_stream" AS
SELECT 
    symbol,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as window_start,
    DATEADD(MINUTE, 15, ROWTIME_TO_TIMESTAMP(ROWTIME)) as window_end,
    
    -- OHLCV calculations
    (ARRAY_AGG(price ORDER BY timestamp ASC))[1] as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    (ARRAY_AGG(price ORDER BY timestamp DESC))[1] as close_price,
    SUM(volume) as total_volume,
    COUNT(*) as tick_count,
    
    -- Metadata
    'LIVE' as data_source,
    '15m' as interval_type
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL 
  AND price > 0 
  AND volume > 0
GROUP BY 
    symbol,
    ROWTIME_RANGE INTERVAL '15' MINUTE;

-- ===============================================
-- 1-Hour OHLCV Aggregation
-- ===============================================

CREATE OR REPLACE STREAM "ohlcv_1hour_stream" AS
SELECT 
    symbol,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as window_start,
    DATEADD(HOUR, 1, ROWTIME_TO_TIMESTAMP(ROWTIME)) as window_end,
    
    -- OHLCV calculations
    (ARRAY_AGG(price ORDER BY timestamp ASC))[1] as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    (ARRAY_AGG(price ORDER BY timestamp DESC))[1] as close_price,
    SUM(volume) as total_volume,
    COUNT(*) as tick_count,
    
    -- Metadata
    'LIVE' as data_source,
    '1h' as interval_type
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL 
  AND price > 0 
  AND volume > 0
GROUP BY 
    symbol,
    ROWTIME_RANGE INTERVAL '1' HOUR;

-- ===============================================
-- Price Movement Detection
-- ===============================================

CREATE OR REPLACE STREAM "price_movements_stream" AS
SELECT 
    symbol,
    price as current_price,
    LAG(price, 1) OVER (
        PARTITION BY symbol 
        ORDER BY ROWTIME RANGE INTERVAL '5' MINUTE PRECEDING
    ) as previous_price,
    
    -- Calculate percentage change
    CASE 
        WHEN LAG(price, 1) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '5' MINUTE PRECEDING
        ) IS NOT NULL AND LAG(price, 1) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '5' MINUTE PRECEDING
        ) > 0
        THEN ((price - LAG(price, 1) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '5' MINUTE PRECEDING
        )) / LAG(price, 1) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '5' MINUTE PRECEDING
        )) * 100
        ELSE 0
    END as price_change_percent,
    
    volume,
    timestamp,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as processing_time
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL AND price > 0;

-- ===============================================
-- Volume Spike Detection
-- ===============================================

CREATE OR REPLACE STREAM "volume_spikes_stream" AS
SELECT 
    symbol,
    volume as current_volume,
    AVG(volume) OVER (
        PARTITION BY symbol 
        ORDER BY ROWTIME RANGE INTERVAL '1' HOUR PRECEDING
    ) as avg_volume_1h,
    
    -- Volume spike ratio
    CASE 
        WHEN AVG(volume) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '1' HOUR PRECEDING
        ) > 0
        THEN volume / AVG(volume) OVER (
            PARTITION BY symbol 
            ORDER BY ROWTIME RANGE INTERVAL '1' HOUR PRECEDING
        )
        ELSE 1
    END as volume_spike_ratio,
    
    price,
    timestamp,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as processing_time
FROM "SOURCE_SQL_STREAM_001"
WHERE symbol IS NOT NULL AND volume > 0;

-- ===============================================
-- Significant Price Alerts
-- ===============================================

CREATE OR REPLACE STREAM "price_alerts_stream" AS
SELECT 
    symbol,
    price,
    price_change_percent,
    'SIGNIFICANT_MOVE' as alert_type,
    CASE 
        WHEN price_change_percent > 5 THEN 'HIGH'
        WHEN price_change_percent > 2 THEN 'MEDIUM'
        ELSE 'LOW'
    END as severity,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as alert_time
FROM "price_movements_stream"
WHERE ABS(price_change_percent) > 1.0  -- Alert on > 1% moves
AND previous_price IS NOT NULL;

-- ===============================================
-- Volume Alerts
-- ===============================================

CREATE OR REPLACE STREAM "volume_alerts_stream" AS
SELECT 
    symbol,
    current_volume,
    avg_volume_1h,
    volume_spike_ratio,
    'VOLUME_SPIKE' as alert_type,
    CASE 
        WHEN volume_spike_ratio > 5 THEN 'HIGH'
        WHEN volume_spike_ratio > 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END as severity,
    ROWTIME_TO_TIMESTAMP(ROWTIME) as alert_time
FROM "volume_spikes_stream"
WHERE volume_spike_ratio > 2.0;  -- Alert on 2x volume spikes
