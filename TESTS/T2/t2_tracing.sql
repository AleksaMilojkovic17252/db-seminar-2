SET tracing = on;
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 9000;
COMMIT;
SET tracing = off;

SHOW TRACE FOR SESSION;
