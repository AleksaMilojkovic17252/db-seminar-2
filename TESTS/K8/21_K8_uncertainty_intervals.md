# K8 — Uncertainty Intervals

## Goal and Hypothesis
Trigger and directly observe `ReadWithinUncertaintyIntervalError` — the mechanism that
buys K1's no-stale-reads guarantee without atomic clocks. The uncertainty interval is not
about *actual* clock skew; it's about *possible* skew. A transaction with timestamp `T`
carries an uncertainty window `[T, T+max_offset]`; any value it encounters with an MVCC
timestamp in that window *might* have been committed by a node whose clock runs ahead, so
it can't be safely ignored. CockroachDB narrows this using observed timestamps — once a
transaction has talked to a node, it knows that node's clock reading and can rule out
"future" values from it. The recipe exploits this directly: make transaction [A] read from
a leaseholder it has never contacted.

## Attempt 1 — 0/100, logged INCONCLUSIVE, then rigorously diagnosed
A 100-attempt scripted version (`K1=id=1`, `K2=id=9000`, gatewayed through n1) produced
**zero** uncertainty errors, zero other errors, 100 clean commits, and a flat
`txn.restarts.readwithinuncertainty` counter (0 before and after). Per the protocol's own
instruction, this was not treated as a failure to paper over — it was logged
`INCONCLUSIVE` and investigated.

Three specific candidate causes, each directly tested rather than assumed:
1. **Gateway/leaseholder overlap.** A's gateway was n1, and (per SETUP-3 at the time)
   `id=9000`'s leaseholder was also n1 — meaning A never had to leave its own node to
   read K2. Directly tested by switching A's gateway to n3 (confirmed to hold neither
   key's lease) and re-running. **Result: still 0/100 — refuted.**
2. **Timing budget exceeded.** Directly measured by instrumenting the critical window
   (A's first read through A's second read): median 10.65ms, max 28.93ms, against the
   500ms budget — nowhere close. **Refuted, not marginal.**
3. **Silent server-side retry via unflushed results.** The script's `results_buffer_size
   = 0` line was wrapped in a silent try/except; checked directly via `SHOW
   results_buffer_size` and confirmed to be a real, existing setting (default `524288`).
   **Ruled out as an obviously-missing setting**, though see the resolution below for a
   more precise revision of this theory.

**A genuine, unplanned side-finding surfaced during this diagnosis:** `SHOW RANGES`
revealed the accounts table's leaseholder layout had actually *changed* since SETUP-3
(likely from the intervening K7 cluster restarts) — `id=1` and `id=9000` had effectively
swapped leaseholders. This is a real, citable methodological point: lease assignments are
not permanently fixed and should be re-verified before any experiment depending on
specific node identities, not assumed stable from an earlier measurement.

All three candidates were tested and refuted using the *correct, current* topology.

## Resolution — a timestamp-instrumented diagnostic
Rather than continue generating untested theories, a smaller (5-attempt) script was built
to directly measure A's fixed HLC timestamp (`cluster_logical_timestamp()`) and B's
actual commit timestamp (`crdb_internal_mvcc_timestamp`, the same technique already used
successfully in K3/K4) and compute the real gap.

**Result: 5/5 hits.** Every attempt raised `ReadWithinUncertaintyIntervalError` with full,
specific error text, e.g.:
```
ReadWithinUncertaintyIntervalError: read at time 1784792719.269147952,0 encountered
previous write with future timestamp 1784792719.271214149,0 within uncertainty interval
`t <= (local=1784792719.276356043,0, global=1784792719.769147952,0)`; observed
timestamps: [{1 ...} {2 ...} {3 ...}]
```
Gaps between A's read and B's write timestamp: 1.4–2.1ms across all 5 attempts. The
**local, observed-timestamp-narrowed window** was only ~5.6–8.2ms wide — roughly 60–90×
tighter than the raw 500ms `max_offset` bound, and B's write reliably landed comfortably
inside it every time.

## Interpretation
The mechanism is real, reliable, and confirmed directly. The precision of this data
strongly suggests the original 100-attempt script was meeting every precondition on every
attempt too, and its errors were being **silently absorbed by a transparent server-side
retry** rather than never occurring — revising the earlier "ruled out" conclusion on the
buffering theory: the setting existing didn't guarantee it achieved the intended
eager-flush effect for that exact driver/statement pattern. The best-supported (though not
conclusively isolated) explanation is that the diagnostic script's extra
`cluster_logical_timestamp()` call, issued on A's same cursor immediately after the first
read, forced an early materialization of results that the original script's approach did
not reliably achieve.

Both the `INCONCLUSIVE` (200 total attempts across two topologies) and the `CONFIRMED`
(5/5) results are kept in the record, not one overwriting the other — together they show
a genuinely useful distinction: "the mechanism doesn't fire" vs. "the mechanism fires but
a naive client can fail to observe it," which is itself a citable methodological point
about how easy this specific anomaly is to accidentally miss.

## Confidence
`High` for the mechanism itself (repeated, textbook error text, full diagnostic data).
`Medium` for the specific explanation of why the original script never surfaced it — a
well-reasoned account, not a controlled isolation of that one variable.

## Paper Hook
§3.5. The observed-timestamp-narrowing numbers (6–8ms actual vs. 500ms nominal) are a
strong, precise exhibit. The near-miss with transparent retry absorption is worth its own
sentence in Methods as a warning to anyone replicating this experiment. The leaseholder-
drift side-finding belongs in Threats to Validity.
