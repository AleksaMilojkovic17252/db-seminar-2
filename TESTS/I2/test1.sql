-- [A] n1, terminal, leave open
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
SELECT count(*) FROM accounts WHERE balance > 9999;

-- [B] any session
INSERT INTO accounts (id, owner, balance, region) VALUES (99999, 'phantom', 99999, 'eu-west-1');

-- [A]
SELECT count(*) FROM accounts WHERE balance > 9999;
COMMIT;

