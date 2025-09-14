-- Drop existing table if it exists
DROP TABLE IF EXISTS raw_ohlcv;

-- Create the new table with proper schema
CREATE TABLE raw_ohlcv (
    symbol VARCHAR(20) NOT NULL,
    open DECIMAL(12,4) NOT NULL,
    high DECIMAL(12,4) NOT NULL,
    low DECIMAL(12,4) NOT NULL,
    close DECIMAL(12,4) NOT NULL,
    volume BIGINT NOT NULL,
	interval VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    -- Add a primary key constraint
    PRIMARY KEY (symbol, timestamp, interval)
);

-- Convert to TimescaleDB hypertable (this is the key TimescaleDB feature!)
-- This partitions the data by time for optimal performance
SELECT create_hypertable('raw_ohlcv', 'timestamp');

-- Create indexes for better query performance
CREATE INDEX idx_raw_ohlcv_symbol ON raw_ohlcv (symbol);
CREATE INDEX idx_raw_ohlcv_timestamp_desc ON raw_ohlcv (timestamp DESC);
CREATE INDEX idx_raw_ohlcv_symbol_timestamp ON raw_ohlcv (symbol, timestamp DESC);

-- Set chunk time interval (default is 7 days, but we can customize)
-- For daily data, 30 days per chunk might be good
SELECT set_chunk_time_interval('raw_ohlcv', INTERVAL '30 days');

-- Enable compression for older data (great for storage efficiency)
ALTER TABLE raw_ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,interval',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Set up automatic compression for chunks older than 30 days
SELECT add_compression_policy('raw_ohlcv', INTERVAL '30 days');
