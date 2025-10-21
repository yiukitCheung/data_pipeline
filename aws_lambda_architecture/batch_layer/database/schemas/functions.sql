-- Create Function that fetch the symbol ohlcv in a given date range
CREATE OR REPLACE FUNCTION Fetch_Symbol_Range(
    p_symbol VARCHAR(10),  -- Parameter for the stock symbol
    p_days INTEGER         -- Parameter for the number of days back
)
-- Define the structure of the data this function will return
RETURNS TABLE (
    open_p DECIMAL,
    high_p DECIMAL,
    close_p DECIMAL,
    low_p DECIMAL,
    volume_p BIGINT,
    ts_p TIMESTAMP
)
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.open, r.high, r.close, r.low, r.volume, r.timestamp
    FROM 
        raw_ohlcv r
    WHERE 
        r.symbol = p_symbol
        -- Correct PostgreSQL date arithmetic: multiply the INTEGER parameter by a 1-day INTERVAL
    AND 
        r.timestamp >= CURRENT_DATE - (p_days * INTERVAL '1 day') 
    ORDER BY 
        r.timestamp ASC;
END;
$$ LANGUAGE plpgsql;

-- Create Function that fetch the YTD/ MTD symbol ohlcv
CREATE OR REPLACE FUNCTION Fetch_Symbol_Period(
    p_symbol VARCHAR(10),             -- 1. Mandatory (no default)
    p_period_type VARCHAR(3),         -- 2. Mandatory (no default)
    p_end_date DATE DEFAULT CURRENT_DATE -- 3. Optional (has a default), must be last
)
RETURNS TABLE (
    open_p DECIMAL,
    high_p DECIMAL,
    close_p DECIMAL,
    low_p DECIMAL,
    volume_p BIGINT,
    ts_p TIMESTAMP
)
AS $$
DECLARE
    v_start_date DATE;
BEGIN
    IF p_period_type = 'YTD' THEN
        v_start_date := DATE_TRUNC('year', p_end_date)::DATE;
    ELSIF p_period_type = 'MTD' THEN
        v_start_date := DATE_TRUNC('month', p_end_date)::DATE;
    ELSE
        RAISE EXCEPTION 'Unsupported period type: %', p_period_type;
    END IF;

    RETURN QUERY
	    SELECT 
	        r.open, r.high, r.close, r.low, r.volume, r.timestamp
	    FROM 
	        raw_ohlcv r
	    WHERE 
	        r.symbol = p_symbol
	    AND 
	        r.timestamp >= v_start_date
	    AND
	        r.timestamp <= p_end_date
	    ORDER BY 
	        r.timestamp ASC;
END;
$$ LANGUAGE plpgsql;

--Create Growth Calculation Function
CREATE OR REPLACE FUNCTION Growth(
	p_symbol,
	p_days
)


-- Test Function

-- Test Fetch Symbol Range
SELECT * FROM Fetch_Symbol_Range('AAPL', 30)
-- Test Fetch Symbol Period
SELECT * FROM Fetch_Symbol_Period('AAPL', 'YTD')


