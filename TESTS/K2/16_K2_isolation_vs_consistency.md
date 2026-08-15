# K2 — Reads Block on Writes, and It Is Consistency, Not Isolation

## Goal and Hypothesis
Directly test (and, going in, falsify) the most common misconception about CockroachDB:
that a reader blocking on a concurrent writer is caused by isolation level, and can be
"fixed" by weakening it. **Hypothesis:** a reader blocks for essentially the same duration
(~3s, matching a held write) regardless of whether it requests SERIALIZABLE, REPEATABLE
READ, or READ COMMITTED — because the blocking is caused by consistency requirements
(a reader can't safely ignore a live intent without risking a stale read), not by
isolation semantics.

## Procedure
A Python/threading script: a writer holds an intent open on `accounts.balance` for 3
seconds; a reader thread, running at a configurable isolation level (proven via `SHOW
transaction_isolation`), attempts to read the same row and is timed. Run 5 times per level
(R4's minimum) across all three levels.

## First Run — refuted the hypothesis for 2 of 3 levels
| Level | blocked_median | Value seen |
|---|---|---|
| SERIALIZABLE | 3.009s | pre-write value |
| REPEATABLE READ | **0.005s** | pre-write value |
| READ COMMITTED | **0.005s** | pre-write value |

Only SERIALIZABLE blocked as predicted. REPEATABLE READ and READ COMMITTED both returned
the last-committed value almost instantly.

## Diagnostic Re-Run — ruling out a script artifact before accepting the result
Before treating this as a real finding, one concrete alternative explanation was tested
directly rather than assumed away: the script had no explicit `commit()` between the
isolation-proof check and the timed read, so the reader's actual transaction boundary
(and its pinned read timestamp) might have been fixed earlier than intended. An explicit
`commit()` was inserted immediately before the timed read, forcing a genuinely fresh
transaction boundary, and the whole experiment re-run.

**Result: identical.** REPEATABLE READ and READ COMMITTED still returned in ~0.005s. This
rules out the early-pinned-snapshot theory and confirms the original result is real, not
a script artifact.

## Interpretation
Only SERIALIZABLE actually blocks on the intent; the other two levels sidestep it. This
does **not** violate K1's no-stale-reads guarantee — both fast reads started and completed
*before* the writer ever committed, so returning the pre-write value is the correct
answer for a read at that real time, not a stale one.

Best available explanation, offered with appropriate hedging (inferred from behavior, not
independently verified against internals): SERIALIZABLE requires a strict, single global
ordering consistent with real time, so to place itself correctly relative to a live,
in-flight write, it genuinely has to resolve that write's eventual fate — which means
waiting. REPEATABLE READ and READ COMMITTED only need to return *a* value valid as of
*some* legitimate past read timestamp, and the last-committed value already satisfies that
without needing to know the pending write's outcome at all.

This reframes the experiment's actual claim, revising rather than confirming the original
hypothesis: isolation level does not change whether reads eventually see committed data
correctly — but it does change whether a reader is *forced* to wait on a concurrent
in-flight write it doesn't strictly need to resolve, versus being *permitted* to sidestep
it. Arguably a stronger and more precise statement of "consistency and isolation are
separate axes" than the original hypothesis would have produced if confirmed as stated.

## Confidence
`High` for the behavioral result — reproduced identically across two independent runs
with a controlled variable changed between them. `Medium` for the specific mechanistic
explanation — inferred from observed behavior, not independently verified against
CockroachDB internals or documentation.

## Paper Hook
§2.1/3.4 — likely a stronger, more surprising exhibit than the originally planned one. A
three-row table split by "forced to resolve" (SERIALIZABLE) vs. "not required to resolve"
(REPEATABLE READ/READ COMMITTED) is worth its own figure.
