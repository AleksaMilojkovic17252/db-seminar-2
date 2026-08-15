-- [A] gateway n1 -- will insert the PARENT
BEGIN;
SHOW transaction_isolation;
SELECT * FROM comments WHERE id = 1;   -- expect empty; this fixes A's read timestamp
-- STOP HERE

-- [B] gateway n2 -- inserts the CHILD, commits immediately
INSERT INTO comments (id, parent_id, body) VALUES (2, 1, 'OP is wrong');

-- [M] gateway n3 -- leaves a timestamp-cache entry above B's commit
SELECT * FROM comments WHERE id = 1;   -- expect still empty

-- [A]
INSERT INTO comments (id, parent_id, body) VALUES (1, NULL, 'a root comment');
COMMIT;

-- [M]
SELECT id, parent_id, crdb_internal_mvcc_timestamp FROM comments ORDER BY id;