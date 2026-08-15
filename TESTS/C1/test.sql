-- [A] gateway n1
BEGIN;
UPDATE inventory SET stock = stock - 1, version = version + 1 WHERE product_id = 1;
-- STOP HERE, don't commit yet

-- [B] gateway n2 or n3
BEGIN;
UPDATE inventory SET stock = stock - 1, version = version + 1 WHERE product_id = 1;
-- expect this to BLOCK

-- [M]
SELECT lock_key_pretty, txn_id, lock_strength, granted, contended
FROM crdb_internal.cluster_locks WHERE table_name = 'inventory';

-- [A]
COMMIT;

-- [B], once unblocked
COMMIT;

-- [M], after a ~5s pause
SELECT collection_ts, contention_duration, waiting_txn_id, blocking_txn_id,
       waiting_txn_fingerprint_id, blocking_txn_fingerprint_id
FROM crdb_internal.transaction_contention_events
ORDER BY collection_ts DESC LIMIT 5;

