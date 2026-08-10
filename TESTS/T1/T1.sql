-- TERMINAL 1
BEGIN;
UPDATE accounts SET balance = balance - 500 WHERE id = 1;
-- do NOT commit

-- TERMINAL 2
SELECT DISTINCT lock_strength, durability FROM crdb_internal.cluster_locks;
SELECT range_id, table_name, lock_key_pretty, txn_id, ts,
       lock_strength, durability, granted, contended
FROM crdb_internal.cluster_locks
WHERE table_name = 'accounts';

-- TERMINAL 1
COMMIT;

-- TERMINAL 2
SELECT count(*) FROM crdb_internal.cluster_locks WHERE table_name = 'accounts';
