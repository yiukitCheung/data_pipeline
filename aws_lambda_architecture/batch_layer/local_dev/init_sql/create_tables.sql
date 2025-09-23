-- Initialize local TimescaleDB for batch layer testing
-- Purpose: Create tables that match AWS Aurora schema

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create symbol metadata table
CREATE TABLE IF NOT EXISTS test_symbol_metadata (
    symbol VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255),
    market VARCHAR(100),
    locale VARCHAR(100),
    active VARCHAR(100),
    primary_exchange VARCHAR(100),
    type VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

-- Create raw OHLCV table (hypertable for time-series optimization)
CREATE TABLE IF NOT EXISTS test_raw_ohlcv (
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

-- Convert raw_ohlcv to TimescaleDB hypertable
SELECT create_hypertable('test_raw_ohlcv', 'timestamp', if_not_exists => TRUE);

-- Create Fibonacci resampled tables (silver layer)
CREATE TABLE IF NOT EXISTS test_silver_3d (
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

CREATE TABLE IF NOT EXISTS test_silver_5d (
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

CREATE TABLE IF NOT EXISTS test_silver_8d (
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

CREATE TABLE IF NOT EXISTS test_silver_13d (
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

CREATE TABLE IF NOT EXISTS test_silver_21d (
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

CREATE TABLE IF NOT EXISTS test_silver_34d (
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

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_symbol_timestamp ON test_raw_ohlcv(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_ohlcv_timestamp ON test_raw_ohlcv(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_silver_3d_symbol_date ON test_silver_3d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_5d_symbol_date ON test_silver_5d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_8d_symbol_date ON test_silver_8d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_13d_symbol_date ON test_silver_13d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_21d_symbol_date ON test_silver_21d(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_silver_34d_symbol_date ON test_silver_34d(symbol, date DESC);
