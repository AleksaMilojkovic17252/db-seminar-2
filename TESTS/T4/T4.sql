-- [TERMINAL 1] gateway n1 -- leave this window open
BEGIN;
UPDATE accounts SET balance = balance - 1000 WHERE id = 1;
UPDATE accounts SET balance = balance + 1000 WHERE id = 9000;
-- do NOT commit