SET tracing = on;
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
SET tracing = off;

SELECT span_idx, message_idx, operation, tag, message
FROM crdb_internal.session_trace
ORDER BY span_idx, message_idx;
