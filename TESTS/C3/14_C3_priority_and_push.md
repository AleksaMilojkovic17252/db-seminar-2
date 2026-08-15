# C3 — Transaction Priority and the Push Mechanism

## Goal and Hypothesis
Follow up directly on C2's open distribution question: rather than leaving the winner to
arrival-order timing, set priority explicitly (`PRIORITY LOW` / `PRIORITY HIGH`) and check
whether it reliably determines the outcome — and in which specific way.

## Preliminary: metric-name verification
Before measuring, the exact metric names the working protocol assumed
(`txn.restarts.txnpush`, `txn.restarts.txnaborted`) were independently checked against
`crdb_internal.node_metrics` rather than trusted — both confirmed to exist, spelled
exactly as expected, alongside a wider family of related counters
(`txn.restarts.serializable`, `txn.restarts.writetooold`, etc.) that clarified which
counter was actually the right signal to watch for a push-driven (not retry-driven)
resolution.

## Direction 1 — HIGH-priority reader vs. LOW-priority writer

**Hypothesis (as stated in the working protocol):** the HIGH reader pushes the LOW writer
to `ABORTED`; the writer's `COMMIT` fails.

**Result: hypothesis refuted, with a well-evidenced alternative mechanism found.** [A]'s
(LOW, writer) `COMMIT` succeeded — no error. [M]'s (HIGH, reader) `SELECT` returned the
**pre-write** value (`10000.00`) in 7ms, no visible block. The live value after both
committed was `9999.00` — A's write genuinely landed. Metric snapshots (all 3 nodes,
before/after) showed `txn.restarts.txnaborted` delta = **0, exactly**, on every node
individually; `txn.restarts.txnpush` also flat at 0.

**Mechanism identified:** rather than abort, CockroachDB pushed A's commit **timestamp**
forward transparently. Because A's transaction was a single blind write with no internal
read to invalidate, the timestamp push created no inconsistency for A to detect — it
committed cleanly at the new, later timestamp. M's read, needing to return immediately,
correctly reflected state as of M's own (earlier) timestamp — before A's now-later-stamped
write existed from M's point of view.

## Direction 2 — LOW-priority reader vs. HIGH-priority writer

**Hypothesis:** the LOW reader waits for the HIGH writer to commit, rather than being
pushed or erroring — tested without assuming this after direction 1 showed priority can
resolve invisibly.

**Result: confirmed, and mechanistically the mirror image of direction 1.** [A] (HIGH,
writer) committed immediately, no wait. [M] (LOW, reader) **blocked for 37.297s**, then
returned the pre-write value (`9999.00`) — the correct answer, reached by genuinely
waiting rather than by a timestamp push. Metrics again showed exact-zero deltas on both
counters, on every node — this resolution, too, is invisible to the standard retry
counters; it's ordinary lock queuing (the same fundamental mechanism as T1 and C1), just
now shown to be gated by relative priority rather than pure arrival order.

## Interpretation
Both directions ultimately return the value as of the writer's pre-commit state, but reach
it through entirely different mechanisms depending on which side outranks the other: a
transparent timestamp push (invisible, no wait, no error) when the reader outranks the
writer; an ordinary blocking wait when the reader is outranked. Neither mechanism moves
either `txn.restarts` counter — both happen below the level either client-visible retry
metric observes, which is itself a notable methodological finding: priority-based
conflict resolution in CockroachDB is not fully observable through these standard
counters alone.

## Confidence
`High` for both directions — clean block/no-block timing, correct values confirming
genuine mechanism rather than a race, and exact-zero metric deltas across all 3 nodes in
both cases.

## Paper Hook
§3.4. The two directions together are likely the strongest single exhibit in phase C: same
schema, same two transactions, only the priority assignment swapped, producing two
entirely different resolution mechanisms that both converge on the same logical answer.
