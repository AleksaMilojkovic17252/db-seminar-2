-- [A] gateway n1
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
SELECT value FROM counters WHERE id = 1;
-- STOP HERE, don't write yet

-- [B] any session
UPDATE counters SET value = 5 WHERE id = 1;

-- [A] -- "I read 0, so I write 0 + 1"
UPDATE counters SET value = 1 WHERE id = 1;
COMMIT;
SELECT value FROM counters WHERE id = 1