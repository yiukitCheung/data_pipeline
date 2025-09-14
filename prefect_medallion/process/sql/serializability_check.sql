SELECT pid, usename, datname, client_addr, application_name, backend_start, state, state_change,
       CASE
           WHEN xact_start IS NULL THEN 'No active transaction'
           ELSE xact_start::text
       END AS transaction_start_time,
       query
FROM pg_stat_activity
WHERE state IN ('active', 'idle in transaction')
ORDER BY transaction_start_time;


-- -- To terminate a specific backend PID
-- SELECT pg_terminate_backend(72083);