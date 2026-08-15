-- Any Node Any Terminal, measuer baseline
SELECT name FROM crdb_internal.node_metrics
WHERE name LIKE 'txn.restarts%' OR name LIKE '%abort%'
ORDER BY name;

-- [A]
BEGIN PRIORITY LOW;
SHOW transaction_isolation;
UPDATE accounts SET balance = balance - 1 WHERE id = 1;
-- STOP HERE

-- [M]
BEGIN PRIORITY HIGH;
SHOW transaction_isolation;
SELECT balance FROM accounts WHERE id = 1;
COMMIT;

-- [A]
COMMIT;   -- expect: aborted
