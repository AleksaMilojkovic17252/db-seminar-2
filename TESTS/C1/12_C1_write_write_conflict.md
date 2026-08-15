# C1 — Write-Write Conflict and the Lock Wait Queue

## Goal and Hypothesis
Establish the baseline conflict-resolution behavior two ordinary transactions writing the
same row: a genuine FIFO-style wait, not a race and not an error. **Hypothesis:** [B]
blocks until [A] commits; `cluster_locks` shows exactly one granted row and one queued row
while both transactions are open.

## Procedure
[A], real terminal session, holds an open transaction after writing `inventory.stock` for
`product_id=1`. [B], a second real terminal, attempts the identical write and is expected
to block. A third session [M] inspects `cluster_locks` while [B] is blocked. [A] commits;
[B] should unblock and complete on its own. Afterward, `transaction_contention_events` is
queried (after a short pause, since it's recorded asynchronously) as an independent
cross-check on the same event.

Timing method: rather than build a script for a single measurement, `cockroach sql`'s own
interactive shell prints wall-clock execution time on every statement — the same approach
already validated in earlier experiments — so [B]'s own terminal output *is* the timing
measurement.

## Results
`cluster_locks` while [B] was blocked:

| txn | lock_strength | granted |
|---|---|---|
| [A] | Intent | true |
| [B] | Exclusive | false |

[B]'s terminal-reported block time: **21.278s**. The `transaction_contention_events` row
recorded for the same pair of transaction IDs showed `contention_duration = 21.269604s` —
agreeing with [B]'s own terminal timing to within **9 milliseconds**, a strong independent
cross-check rather than a single-source measurement.

## Interpretation
Confirms the hypothesis, validated by two independently-sourced measurements of the same
wait agreeing closely. The lock-strength pattern (`Intent` for the granted writer,
`Exclusive` for the blocked one) matches what was later confirmed repeatedly elsewhere in
the project (T1, I5) — a consistent signature across different tables and different
concurrency scenarios, not a one-off coincidence.

## Confidence
`High` — cross-validated via two independent data sources (terminal timing,
`transaction_contention_events`) agreeing to within milliseconds, not inferred from either
alone.

## Paper Hook
§3.4 (conflict detection). The dual-measurement agreement is itself worth a sentence in
Methods as a validation technique for future timing claims in this project.
