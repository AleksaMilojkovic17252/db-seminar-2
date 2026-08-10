-- 04_reset.sql -- run between experiments to restore the baseline state.
-- Matches protocol SETUP-4 exactly.
UPDATE accounts SET balance = 10000.00 WHERE balance != 10000.00;
UPDATE doctors SET on_call = true;
UPDATE counters SET value = 0 WHERE id = 1;
UPDATE inventory SET stock = 100, version = 1 WHERE stock != 100 OR version != 1;
DELETE FROM comments;
SELECT sum(balance) FROM accounts;  -- must print 100000000.00
