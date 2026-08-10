# I3 — Write Skew

## Goal and Hypothesis
The mirror image of I2: SERIALIZABLE is hypothesized to be the *only* level that prevents
this anomaly, since it's the one anomaly snapshot isolation (CockroachDB's REPEATABLE
READ) is known to permit. Scenario: two on-call doctors; two transactions each
independently read "2 on call" and each take exactly one doctor off-call, believing their
own action is safe. **Hypothesis:** SERIALIZABLE rejects one of the two commits;
REPEATABLE READ and READ COMMITTED allow both through, ending with nobody on call.

## Procedure — a genuine methodological detour, not a straight-line experiment
**First attempt (SERIALIZABLE) collapsed into sequential execution, not concurrency.**
The read step (`COUNT(*) WHERE on_call = true`) has to scan both rows in a 2-row table,
including whichever one the other session is mid-write on. When [B]'s covering read ran
while [A] already held an uncommitted intent on one doctor, [B]'s read simply blocked
(165.887s) until [A] committed, then read post-commit state — never actually observing a
stale, pre-write snapshot the way write skew requires. Both commits then succeeded
cleanly, with no `40001` anywhere, because there was no real conflict left by the time
either commit ran. This was logged as its own `INCONCLUSIVE` entry rather than discarded —
it's a real, citable finding in its own right: a full-table-scan read predicate
inherently serializes with any in-flight write to that table, regardless of isolation
level, which is a genuine limitation of using `COUNT(*)` as the "read" step in a
write-skew demo on a tiny table.

**Second attempt reordered the script** so both sessions' reads complete *before* either
writes: [A] reads and stops; [B] reads (confirmed matching [A]'s count, proving genuine
concurrency), writes, commits; only then does [A] write and attempt to commit.

## Results

| Isolation level | Both commits succeed? | Final on-call count | Write skew? |
|---|---|---|---|
| SERIALIZABLE | No — [A] rejected | 1 | **Prevented** |
| REPEATABLE READ | Yes | 0 | **Permitted** |
| READ COMMITTED | Yes | 0 | **Permitted** |

SERIALIZABLE's rejection, captured verbatim:
```
ERROR: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError:
retry txn (RETRY_SERIALIZABLE - failed preemptive refresh due to encountered recently
written committed value /Table/109/1/2/0 @...): ...
SQLSTATE: 40001
```

## Interpretation
Confirms the hypothesis via the exact mechanism predicted: SERIALIZABLE does not block
[A]'s write against [B]'s — they touch different rows, so there's no lock conflict to
wait on. Instead, [A]'s own *read* is checked at commit time against everything committed
since; [B]'s commit made [A]'s original snapshot stale in a way that would produce write
skew if let through, so the preemptive refresh failed and the commit was rejected
outright, not merely delayed.

REPEATABLE READ and READ COMMITTED both permitted the anomaly, confirming the mirror-image
relationship with I2 flagged in advance: REPEATABLE READ (snapshot isolation) checks
whether *its own* snapshot is internally consistent, but does not check whether a
committed write to a *different* row invalidated the assumption the transaction's logic
was built on — nothing here triggers a refresh failure the way it did for SERIALIZABLE,
which adds a genuine cross-row dependency check on top of the snapshot.

## Confidence
`High` for the genuine concurrent trial at all three levels — SERIALIZABLE's rejection is
captured verbatim; REPEATABLE READ and READ COMMITTED's permissive results are unambiguous
(both commits, count=0). The first SERIALIZABLE attempt's collapse into sequential
execution is logged separately and is not folded into the final result.

## Paper Hook
§3.3, rows 3a/3b/3c. Likely the centerpiece contrast of the whole isolation chapter: same
schema, same script, only the isolation level changed, producing three qualitatively
different outcomes. The blocked-covering-read finding from attempt 1 is worth its own
sentence as a methodology caveat for anyone replicating this experiment.