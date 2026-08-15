# I6 — Isolation and Staleness Interact: READ COMMITTED + AS OF SYSTEM TIME

## Goal and Hypothesis
A sharp, single-shot test of whether pinning a transaction to a historical instant is
compatible with READ COMMITTED's per-statement-fresh-read premise. **Hypothesis (as
stated in the working protocol):** CockroachDB silently *promotes* the combination to a
read-only SERIALIZABLE transaction rather than rejecting it outright — contrasted
explicitly against PostgreSQL, which rejects the combination as an error.

## Procedure
Single session, read-only, no concurrency needed:
```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED AS OF SYSTEM TIME '-10s';
SHOW transaction_isolation;
SELECT balance FROM accounts WHERE id = 1;
COMMIT;
```

## Result
`SHOW transaction_isolation` reported `read committed` — **no promotion**. The transaction
ran and committed normally at the level actually requested.

## Interpretation
**Directly refutes the stated hypothesis.** The predicted incoherence doesn't hold up on
closer inspection: `AS OF SYSTEM TIME '-10s'` fixes the transaction's reference instant to
one specific point in the past, rather than leaving "now" as a moving target. Taking a
"fresh snapshot per statement" against that same fixed historical instant, every time,
produces identical results regardless — there's no real tension for CockroachDB to
resolve by promoting anything. Running the combination literally as written, unmodified,
is arguably the *more* internally consistent behavior, not a compromise position.

## Caveat
The returned balance (`10000.00`) does not independently verify that the historical-
timestamp clause actually changed what was read, since `id=1` had not been written to
since an earlier reset several experiments prior — a live read at the same moment would
have shown an identical value. This result confirms the isolation-level-reporting claim
cleanly; it does not, on its own, independently confirm the read-timestamp mechanics.

## Confidence
`High` for the refutation itself (single, unambiguous `SHOW transaction_isolation`
output). `Low` on independently confirming `AS OF SYSTEM TIME`'s effect on the data read,
given the caveat above — would need a key with more recent write history to test that
specifically.

## Paper Hook
§3.3/3.5. A second directly-evidenced refutation of a specific protocol claim (alongside
I5's FOR SHARE result) with a plausible alternative theoretical account rather than just
"the documentation was wrong" — worth presenting the two refutations together as a
pattern, not as isolated errors.
