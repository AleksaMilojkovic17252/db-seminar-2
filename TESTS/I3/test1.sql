-- [A] gateway n1
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
SELECT count(*) FROM doctors WHERE on_call = true;   -- expect 2
-- do NOT commit yet

-- [B] gateway n2 or n3
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
SELECT count(*) FROM doctors WHERE on_call = true;
UPDATE doctors SET on_call = false WHERE id = 2;
COMMIT;

-- [A]
UPDATE doctors SET on_call = false WHERE id = 1;
COMMIT;   -- expect SQLSTATE 40001
SELECT count(*) FROM doctors WHERE on_call = true;   -- expect 1

