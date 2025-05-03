-- check background transaction
SELECT pid, query, state, wait_event_type, wait_event, backend_start
FROM pg_stat_activity
WHERE state != 'idle';

-- kill all transaction related to certain task 
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state != 'idle'
  AND query ILIKE '%INSERT INTO processed%'
  AND pid <> pg_backend_pid();
  
-- Check duplicates in resampled 
 SELECT
    date,
    symbol,
    interval,
    COUNT(*)
FROM resampled
GROUP BY
    date,
    symbol,
    interval
HAVING COUNT(*) > 1;
