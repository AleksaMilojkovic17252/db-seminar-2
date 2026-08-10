-- [A] gateway n1
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
SELECT value FROM counters WHERE id = 1 FOR UPDATE;   -- expect 0
-- STOP HERE, don't write yet

-- [B] any session
UPDATE counters SET value = 5 WHERE id = 1;
-- expect this to BLOCK, not return immediately

-- [M]
SELECT lock_key_pretty, lock_strength, durability, granted
FROM crdb_internal.cluster_locks WHERE table_name = 'counters';

-- [A]
UPDATE counters SET value = 1 WHERE id = 1;
COMMIT;
SELECT value FROM counters WHERE id = 1;