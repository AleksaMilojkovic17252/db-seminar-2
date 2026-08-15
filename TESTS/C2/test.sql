-- [A] gateway n1
BEGIN;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;

-- [B] gateway n2 or n3
BEGIN;
UPDATE accounts SET balance = balance - 10 WHERE id = 9000;

-- [A] -- this one waits on B
UPDATE accounts SET balance = balance + 10 WHERE id = 9000;

-- [B] -- this one waits on A -> the cycle closes here
UPDATE accounts SET balance = balance + 10 WHERE id = 1;


-- REPEAT 5 TIMES