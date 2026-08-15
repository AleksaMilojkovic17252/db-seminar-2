# I4 — Lost Update

## Goal and Hypothesis
Demonstrate that a naive "read, decide, write" pattern (as opposed to an atomic
`UPDATE ... = value + 1`) can silently lose a concurrent write. A single-statement atomic
increment produces the correct result at every isolation level and would not discriminate
between them at all — the two-statement shape is required to observe this anomaly.
**Hypothesis:** READ COMMITTED permits the lost update; SERIALIZABLE rejects it via a
`40001`. REPEATABLE READ's behavior was deliberately left an open question, to be reported
whichever way it actually fell rather than assumed.

## Procedure
[A] reads `counters.value` (expecting `0`), then — based on that stale read — writes
`value = 1` ("I read 0, so I write 0+1"), simulating application logic that doesn't know
about concurrent writers. [B], a separate session, independently writes `value = 5` in
between [A]'s read and write. Run once per isolation level, with a reset in between.

## Results

| Isolation level | A's write | Final value | Lost update? |
|---|---|---|---|
| READ COMMITTED | succeeded silently | 1 | **Yes** — B's write of 5 lost |
| REPEATABLE READ | rejected, `WriteTooOldError` (40001) | 5 | No — prevented |
| SERIALIZABLE | rejected, `WriteTooOldError` (40001) | 5 | No — prevented |

At both REPEATABLE READ and SERIALIZABLE, the error fired at the `UPDATE` statement
itself, not deferred to `COMMIT` — a real, checkable mechanistic difference from I3, where
SERIALIZABLE's rejection came at commit time via a read-set staleness check
(`RETRY_SERIALIZABLE`). Here the conflict is caught immediately as a direct write-write
timestamp collision (`WriteTooOldError`) — two different detection mechanisms, both
surfacing under the same `40001` SQLSTATE.

The REPEATABLE READ error's own metadata included `iso=Snapshot` — a literal, engine-level
confirmation (not just an SQL-surface label) that CockroachDB's REPEATABLE READ really is
running as snapshot isolation internally.

## Interpretation
Confirms the read-decide-write shape is necessary to observe this anomaly at all —
distinguished explicitly from I1's similar two-statement shape, where A's *read* silently
changes; here A's *write* silently destroys B's committed write based on stale
information. REPEATABLE READ landed on the SERIALIZABLE side for this anomaly, not the
READ COMMITTED side — consistent with both being snapshot-based under the hood, and
resolving the open question the hypothesis deliberately left unstated.

## Confidence
`High` across all three levels — error text captured verbatim in both rejection cases,
B's write independently confirmed via its own output in every trial, and the final value
checked explicitly rather than inferred.

## Paper Hook
§3.3, row 4 of the isolation-level anomaly table. The `iso=Snapshot` detail in the
REPEATABLE READ error metadata is a strong, quotable, literal confirmation of "REPEATABLE
READ is snapshot isolation," worth using as a direct exhibit rather than an assertion.
