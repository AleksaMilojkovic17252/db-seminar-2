SELECT balance FROM accounts AS OF SYSTEM TIME follower_read_timestamp() WHERE id = 9000;
SELECT balance FROM accounts AS OF SYSTEM TIME with_max_staleness('10s') WHERE id = 9000;
SELECT balance FROM accounts AS OF SYSTEM TIME with_max_staleness('10s', true) WHERE id = 9000;

EXPLAIN (VERBOSE) SELECT balance FROM accounts
AS OF SYSTEM TIME follower_read_timestamp() WHERE id = 9000;

SELECT a.balance, b.balance FROM accounts a JOIN accounts b ON a.id = b.id - 1
AS OF SYSTEM TIME with_max_staleness('10s') LIMIT 1;