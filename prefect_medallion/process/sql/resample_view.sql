WITH numbered AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date) AS rn
    FROM raw_data
),
grp AS (
    SELECT
        *,
        (rn - 1) / {interval} AS grp_id
    FROM numbered
)
SELECT
    symbol,
    MIN(date)   AS date,
    FIRST(open) AS open,
    MAX(high)   AS high,
    MIN(low)    AS low,
    LAST(close) AS close,
    SUM(volume) AS volume
FROM grp
GROUP BY symbol, grp_id 