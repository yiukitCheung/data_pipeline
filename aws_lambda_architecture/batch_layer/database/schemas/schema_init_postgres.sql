-- ============================================================================
-- PostgreSQL Schema Initialization for AWS RDS (WITHOUT TimescaleDB)
-- ============================================================================
-- Purpose: Initialize production database schema for condvest batch layer
-- Usage: Copy and paste this entire script into pgAdmin Query Tool
-- Date: 2025-09-28
-- Note: This version works with standard RDS PostgreSQL
-- ============================================================================

-- Step 1: Create symbol metadata table
CREATE TABLE IF NOT EXISTS symbol_metadata (
    symbol VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255),
    market VARCHAR(100),
    locale VARCHAR(100),
    active VARCHAR(100),
    primary_exchange VARCHAR(100),
    type VARCHAR(100),
    marketCap BIGINT,
    sector VARCHAR(50),
    industry VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Create raw OHLCV table (standard PostgreSQL)
CREATE TABLE IF NOT EXISTS raw_ohlcv (
    symbol VARCHAR(50) NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    interval VARCHAR(10) NOT NULL DEFAULT '1d',
    PRIMARY KEY (symbol, timestamp, interval)
);

-- Step 3: Create Fibonacci resampled tables (silver layer)
-- 3D interval table
CREATE TABLE IF NOT EXISTS silver_3d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 5D interval table
CREATE TABLE IF NOT EXISTS silver_5d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 8D interval table
CREATE TABLE IF NOT EXISTS silver_8d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 13D interval table
CREATE TABLE IF NOT EXISTS silver_13d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 21D interval table
CREATE TABLE IF NOT EXISTS silver_21d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- 34D interval table
CREATE TABLE IF NOT EXISTS silver_34d (
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(10,2) NOT NULL,
    high DECIMAL(10,2) NOT NULL,
    low DECIMAL(10,2) NOT NULL,
    close DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Step 4: Create performance indexes
-- Raw OHLCV indexes (optimized for time-series queries)
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_symbol_timestamp ON raw_ohlcv(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_timestamp ON raw_ohlcv(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_interval ON raw_ohlcv(interval);
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_symbol ON raw_ohlcv(symbol);

-- Symbol metadata indexes
CREATE INDEX IF NOT EXISTS idx_symbol_metadata_active ON symbol_metadata(active);
CREATE INDEX IF NOT EXISTS idx_symbol_metadata_type ON symbol_metadata(type);
CREATE INDEX IF NOT EXISTS idx_symbol_metadata_market ON symbol_metadata(market);

-- Silver table indexes (optimized for date range queries)
CREATE INDEX IF NOT EXISTS idx_silver_3d_symbol_date ON silver_3d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_3d_date ON silver_3d(date DESC);

CREATE INDEX IF NOT EXISTS idx_silver_5d_symbol_date ON silver_5d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_5d_date ON silver_5d(date DESC);

CREATE INDEX IF NOT EXISTS idx_silver_8d_symbol_date ON silver_8d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_8d_date ON silver_8d(date DESC);

CREATE INDEX IF NOT EXISTS idx_silver_13d_symbol_date ON silver_13d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_13d_date ON silver_13d(date DESC);

CREATE INDEX IF NOT EXISTS idx_silver_21d_symbol_date ON silver_21d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_21d_date ON silver_21d(date DESC);

CREATE INDEX IF NOT EXISTS idx_silver_34d_symbol_date ON silver_34d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_34d_date ON silver_34d(date DESC);

-- Step 5: PostgreSQL-specific optimizations for time-series data
-- Partition raw_ohlcv by month for better performance (optional)
-- Note: You can implement partitioning later as data grows

-- -- Step 6: Insert sample symbol metadata
-- INSERT INTO symbol_metadata (symbol, name, market, locale, active, primary_exchange, type) VALUES 
-- ('AAPL', 'Apple Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
-- ('MSFT', 'Microsoft Corporation', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
-- ('GOOGL', 'Alphabet Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
-- ('TSLA', 'Tesla Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS'),
-- ('AMZN', 'Amazon.com Inc.', 'stocks', 'us', 'true', 'NASDAQ', 'CS')
-- ON CONFLICT (symbol) DO NOTHING;

-- Step 7: Update table statistics for query optimization
ANALYZE symbol_metadata;
ANALYZE raw_ohlcv;
ANALYZE silver_3d;
ANALYZE silver_5d;
ANALYZE silver_8d;
ANALYZE silver_13d;
ANALYZE silver_21d;
ANALYZE silver_34d;

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- Run these to verify everything was created successfully:

-- Check all tables exist
SELECT 
    schemaname,
    tablename,
    tableowner
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('symbol_metadata', 'raw_ohlcv', 'silver_3d', 'silver_5d', 'silver_8d', 'silver_13d', 'silver_21d', 'silver_34d')
ORDER BY tablename;

-- Check indexes
SELECT 
    indexname,
    tablename
FROM pg_indexes 
WHERE schemaname = 'public' 
AND tablename IN ('symbol_metadata', 'raw_ohlcv', 'silver_3d', 'silver_5d', 'silver_8d', 'silver_13d', 'silver_21d', 'silver_34d')
ORDER BY tablename, indexname;

-- -- Check sample data
-- SELECT COUNT(*) as symbol_count FROM symbol_metadata;
-- SELECT symbol, name FROM symbol_metadata LIMIT 5;

-- Check table sizes
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('symbol_metadata', 'raw_ohlcv', 'silver_3d', 'silver_5d', 'silver_8d', 'silver_13d', 'silver_21d', 'silver_34d')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================================================
-- Success Message
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '==========================================================';
    RAISE NOTICE 'PostgreSQL schema initialization completed successfully!';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - symbol_metadata (metadata for stock symbols)';
    RAISE NOTICE '  - raw_ohlcv (daily price data)';
    RAISE NOTICE '  - silver_3d to silver_34d (Fibonacci resampled data)';
    RAISE NOTICE 'Performance indexes created for time-series queries';
    RAISE NOTICE 'Your batch layer is ready for data ingestion!';
    RAISE NOTICE '==========================================================';
END $$;
