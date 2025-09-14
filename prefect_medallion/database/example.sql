-- select * from processed_staging;
select * from resampled where symbol = 'AESI' and interval = 1 order by date desc;

select * from raw where symbol = 'AESI' order by date desc;
-- select * from resampled_staging

Truncate table  resampled
SELECT 
    symbol, 
    MAX(date) AS max_date
FROM resampled
WHERE interval = '1'
GROUP BY symbol
ORDER BY max_date ASC;

DELETE FROM raw
WHERE ctid IN (
    SELECT ctid FROM (
        SELECT ctid,
               ROW_NUMBER() OVER (PARTITION BY symbol, high, close, low, open, volume ORDER BY date DESC) AS rn
        FROM raw
    ) t
    WHERE t.rn > 1
);

-- CREATE OR REPLACE VIEW resampled_clean AS
-- SELECT *
-- FROM resampled
-- WHERE candle_id is not null;

-- ALTER TABLE resampled RENAME TO resampled_backup;

-- CREATE TABLE resampled AS
-- SELECT *
-- FROM resampled_clean;
-- Check constraints on resampled

-- SELECT 
--     p.date, 
--     p.symbol, 
--     p.interval, 
--     p.value, 
--     i.indicator_id,
--     r.open,
--     r.high,
--     r.low,
--     r.close,
--     r.volume
-- FROM processed AS p
-- INNER JOIN resampled AS r
--     ON p.symbol = r.symbol 
--    AND p.interval::INT = r.interval 
--    AND p.date = r.date
-- INNER JOIN indicator_definitions AS i
--     ON p.indicator_id = i.indicator_id
-- WHERE p.interval = '1' AND p.symbol = 'AAPL'
--   AND p.date >= NOW() - INTERVAL '5 years'
--   AND p.indicator_id IN (2, 3, 8, 10)
-- ORDER BY p.symbol, p.date DESC;

-- SELECT * FROM alerts WHERE alert_type = 'accumulation' ORDER BY date DESC;
-- SELECT* FROM signals ORDER BY date DESC;

-- CREATE OR REPLACE VIEW raw_test_view AS
-- SELECT *
-- FROM raw
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');  -- Replace with your test symbols

-- CREATE OR REPLACE VIEW resampled_test_view AS
-- SELECT *
-- FROM resampled
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');

-- CREATE OR REPLACE VIEW alerts_test_view AS
-- SELECT *
-- FROM alerts
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');

-- CREATE OR REPLACE VIEW signals_test_view AS
-- SELECT *
-- FROM signals
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');

-- CREATE OR REPLACE VIEW processed_test_view AS
-- SELECT *
-- FROM processed
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');

-- CREATE OR REPLACE VIEW symbol_metadata_test_view AS
-- SELECT *
-- FROM symbol_metadata
-- WHERE symbol IN ('AAPL', 'TSLA', 'GOOGL');

SELECT symbol, interval, MAX(date) as lastest_date, MAX(candle_id) as latest_candle_id, status
FROM resampled
WHERE status = 'in_progress'
GROUP BY status, symbol, interval
order by symbol, interval desc, lastest_date desc


WITH combined AS (
	SELECT symbol, interval, MAX(candle_id) AS latest_candle_id, MAX(date) AS lastest_date, status
	FROM resampled
	GROUP BY symbol, interval, status
),
	ranked AS (
		SELECT *,
			   ROW_NUMBER() OVER (PARTITION BY symbol, interval ORDER BY lastest_date DESC) AS rn
		FROM combined
	)
SELECT symbol, interval, latest_candle_id, lastest_date
FROM ranked
WHERE rn = 1;

-- Fetch the latest candle from current resampled data
-- Used in Production Mode Resampling
SELECT 
    r.*, 
    c.lastest_date,
    c.interval,
    c.latest_candle_id,
    c.status
FROM raw r
LEFT JOIN (
    SELECT symbol, interval, lastest_date, latest_candle_id, status
    FROM (
        SELECT 
            symbol, 
            interval,
            status,
            MAX(date) AS lastest_date,
            MAX(candle_id) AS latest_candle_id,
            ROW_NUMBER() OVER (
                PARTITION BY symbol, interval
                ORDER BY 
                    CASE status WHEN 'completed' THEN 1 ELSE 2 END,
                    MAX(date) DESC
            ) AS rn
        FROM resampled
        GROUP BY symbol, interval, status
    ) ranked_status
    WHERE rn = 1
) c
ON r.symbol = c.symbol
WHERE r.date >= c.lastest_date
ORDER BY c.status, r.symbol, c.interval, r.date;


CREATE OR REPLACE VIEW latest_resampled AS
SELECT 
    r.*, 
    c.latest_date,
    c.interval,
    c.latest_candle_id,
    c.status
FROM raw r
LEFT JOIN (
    SELECT symbol, interval, latest_date, latest_candle_id, status
    FROM (
        SELECT 
            symbol, 
            interval,
            status,
            MAX(date) AS latest_date,
            MAX(candle_id) AS latest_candle_id,
            ROW_NUMBER() OVER (
                PARTITION BY symbol, interval
                ORDER BY 
                    CASE status WHEN 'completed' THEN 1 ELSE 2 END,
                    MAX(date) DESC
            ) AS rn
        FROM resampled
        GROUP BY symbol, interval, status
    ) ranked_status
    WHERE rn in (1,2)
) c ON r.symbol = c.symbol
WHERE r.date >= c.latest_date;

-- Find the latest cut-off date from resampled table
CREATE OR REPLACE VIEW latest_resampled AS
SELECT 
    r.*, 
    c.latest_date,
    c.interval,
    c.latest_candle_id,
    c.status
FROM raw r
LEFT JOIN (
    SELECT symbol, interval, latest_date, latest_candle_id, status
    FROM (
        SELECT 
            symbol, 
            interval,
            status,
            MAX(date) AS latest_date,
            MAX(candle_id) AS latest_candle_id
        FROM resampled
        GROUP BY symbol, interval, status
    ) all_statuses
) c ON r.symbol = c.symbol
WHERE r.date >= c.latest_date;

SELECT * FROM latest_resampled where interval = 3 order by date asc

-- Find the latest date of each symbol from raw
WITH latest_date AS (
                    SELECT MAX(date) as max_date 
                    FROM raw
                )
                SELECT date, symbol, close 
                FROM raw 
                WHERE date = (SELECT max_date FROM latest_date)
				
-- drop record conditionally
DELETE FROM resampled
WHERE date >= '2025-04-11';

SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;
WITH symbol_max AS (
    SELECT symbol, MAX(date) AS symbol_max_date
    FROM raw
    GROUP BY symbol
),
overall_max AS (
    SELECT MAX(symbol_max_date) AS max_date FROM symbol_max
)
-- SELECT symbol
-- FROM symbol_max
-- WHERE symbol_max_date < (SELECT max_date FROM overall_max)
-- ORDER BY symbol_max_date ASC;


DELETE FROM raw
WHERE symbol IN (
    SELECT symbol
	FROM symbol_max
	WHERE symbol_max_date < (SELECT max_date FROM overall_max)
	ORDER BY symbol_max_date ASC
);

DELETE FROM symbol_metadata
WHERE symbol IN (
	SELECT symbol
	FROM symbol_max
	WHERE symbol_max_date < (SELECT max_date FROM overall_max)
	ORDER BY symbol_max_date ASC
)

-- Sample: Delete symbols whose max date is not the latest
DELETE FROM raw
WHERE symbol IN (
  SELECT symbol
  FROM (
    SELECT symbol, MAX(date) AS symbol_max_date
    FROM raw
    GROUP BY symbol
  ) AS sm
  WHERE symbol_max_date < (SELECT MAX(date) FROM raw)
)
AND date <= (SELECT MAX(date) FROM raw);