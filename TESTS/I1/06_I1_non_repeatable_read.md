# I1 — Non-Repeatable Read

## Goal and Hypothesis
Demonstrate the isolation-level boundary for the simplest classic anomaly: a value read
twice inside one transaction changing between reads because another transaction committed
in between. **Hypothesis:** allowed at READ COMMITTED; prevented at REPEATABLE READ and
SERIALIZABLE.

## Procedure
Every trial in this phase carries a standing precondition: each transaction must print
`SHOW transaction_isolation` inside itself as proof of the level actually in effect — an
isolation result without that proof is not trusted. Each anomaly runs at all three levels.

Shape used for I1: session **[A]** opens a transaction at the level under test, proves its
isolation level, reads `accounts.balance` for `id=1`. Session **[B]**, a separate
connection, runs a single implicit-transaction `UPDATE` setting the same row to `5000`.
[A] then reads the same row again and commits.

A real methodological wrinkle came up on the REPEATABLE READ trial: [A]'s two reads both
returned the original value, which is the *expected* result — but that same output is
also exactly what you'd see if [B] had simply never run at all. Rather than accept a
result that happened to match the hypothesis without ruling out the more mundane
explanation, [B]'s own transcript was required before logging the trial, not just [A]'s
matching numbers. This distinction — "consistent with the hypothesis" vs. "the hypothesis
was actually tested" — mattered enough to hold up logging until it was resolved.

## Results

| Isolation level | 1st read | 2nd read | Anomaly? |
|---|---|---|---|
| READ COMMITTED | 10000.00 | 5000.00 | **Yes** |
| REPEATABLE READ | 10000.00 | 10000.00 | No — prevented |
| SERIALIZABLE | 10000.00 | 10000.00 | No — prevented |

READ COMMITTED's result was self-evidently real — A's second read showed B's *specific*
written value (5000.00), which is only possible if B actually ran and committed. The
REPEATABLE READ and SERIALIZABLE trials both required and received B's own transcript
before being logged.

## Interpretation
READ COMMITTED takes a fresh read per statement, so B's committed write became visible
mid-transaction to A — the anomaly. REPEATABLE READ and SERIALIZABLE both pin the whole
transaction to a single MVCC snapshot; B's write is simply invisible to A within that
transaction, not blocked or delayed. Mechanistically: A's first read leaves an entry in
the timestamp cache, which forces B's write to take a timestamp above A's read
timestamp — B is not held up by A, the two writes are just ordered such that A's snapshot
predates B's commit.

A's `COMMIT` succeeded without error at every level, including SERIALIZABLE — worth
noting because later experiments (I3, I4) show SERIALIZABLE *rejecting* a commit. I1
involves no write from A, so there is nothing for serializability's conflict-detection
machinery to reject; the anomaly is prevented by the snapshot hiding the write, not by
aborting anything.

## Confidence
`High` across all three levels — isolation proven via `SHOW transaction_isolation` at
each, and B's write independently confirmed via its own output at every level, not
inferred from A's numbers alone.

## Paper Hook
§3.3, row 1 of the isolation-level anomaly table (Figure 4).
