-- [A] n1, terminal, leave open
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
SELECT balance FROM accounts WHERE id = 1;

-- [B] any session
UPDATE accounts SET balance = 5000 WHERE id = 1;

-- Back at [A]
SELECT balance FROM accounts WHERE id = 1;
COMMIT;


