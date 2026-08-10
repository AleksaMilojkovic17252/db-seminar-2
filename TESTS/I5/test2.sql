-- [A] gateway n1
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
SELECT value FROM counters WHERE id = 1 FOR SHARE;
-- STOP HERE

-- [B] any session
UPDATE counters SET value = 5 WHERE id = 1;
-- does this block, or return immediately?

-- [M]
SELECT lock_key_pretty, lock_strength, durability, granted
FROM crdb_internal.cluster_locks WHERE table_name = 'counters';

-- [A]
COMMIT;