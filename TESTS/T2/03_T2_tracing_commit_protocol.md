# T2 — Tracing a Multi-Range vs. Single-Range Transaction

## Goal and Hypothesis

**Goal:** observe transaction pipelining and the commit protocol directly from a trace
(`SHOW TRACE FOR SESSION` / `crdb_internal.session_trace`), rather than inferring them from
latency — justified because loopback RTT is close enough to zero that latency differences
between a 1-round-trip and 2-round-trip commit would be indistinguishable from noise on
this cluster.

**Hypothesis:** a transaction touching two different ranges/leaseholders will show at least
two distinct KV round trips to different ranges, at least one pipelined write, and no 1PC
marker. A contrast transaction on a single range was expected to show fewer round trips and
possibly a 1PC marker.

## Procedure

Both statements of the transaction, plus the tracing `SET` commands, must execute within
one continuous session — stricter than the previous experiment's requirement, since even
`SET tracing = on/off` and the trace read-out are session-scoped, not just the transaction
itself. A GUI database client was considered for this step but avoided given an earlier
experiment's false-negative from client-side autocommit; a genuine interactive terminal
session was used instead.

The raw trace output overflowed the terminal on the first attempt. This was resolved by
writing the tracing block to a `.sql` file and running it non-interactively via
`cockroach sql --file=... > output.txt`, which both guarantees one continuous session (the
same mechanism already trusted for schema seeding) and avoids the overflow entirely by
writing to a file instead of the screen. The narrower `crdb_internal.session_trace` query
(one row per line) was used in place of the wide, wrapped `SHOW TRACE FOR SESSION` display,
since it reads from the same underlying data.

## Finding 1 — Multi-range transaction confirmed: 2 ranges, 2 leaseholders, parallel commits

Run twice (two independent transactions), with consistent results both times.

| Operation | Range | Leaseholder | Dispatch |
|---|---|---|---|
| Get id=1 | r70 | n2 | real RPC to n2 |
| Put id=1 | r70 | n2 | real RPC |
| Get id=9000 | r74 | n1 | local (gateway n1 = r74's leaseholder) |
| Put id=9000 | r74 | n1 | local |
| EndTxn (commit) | r70 | n2 | real RPC |

- **Commit protocol directly named in the trace text:**
  `executing EndTxn(parallel commit) [/Table/106/1/1/0]`.
- **STAGING status directly observed:**
  `making txn commit explicit: ... stat=STAGING ... int=2 ifw=2` — 2 intents, 2
  in-flight-writes, matching the transaction's 2 statements.
- **No `1PC` / `OnePhaseCommit` marker anywhere** — correctly absent, consistent with a
  multi-range transaction.
- **`QueryIntent` absent, and explainable rather than just noted as missing:** parallel
  commits bundles pending-write verification directly into the `EndTxn` request itself
  (`in_flight_writes:<key:... sequence:1 strength:I...>`) rather than issuing a separate
  round trip. `QueryIntent` is the mechanism expected during coordinator-failure recovery,
  not during a clean, successful commit.
- **`async consensus` (the literal trace string) does not appear anywhere in this build's
  output** — a genuine correction to the working protocol's checklist of trace markers,
  logged as such rather than silently worked around.
- **The underlying mechanism was nonetheless demonstrated via timing, more convincingly
  than a string match would have been.** Using a timestamped variant of the trace, both
  individual writes returned from the KV layer to the client in **under 50 microseconds**
  after `proposing command to write...` was logged — far too fast to have waited for actual
  Raft replication. The `EndTxn` (commit), which genuinely must know the outcome before
  reporting success, shows a **~9.4ms** gap between proposing and the `local proposal` /
  `applying command` step completing, measured on the same trial. This is a quantified
  demonstration of write pipelining: individual writes return before consensus completes;
  only the final commit genuinely waits for it.
- **Transaction record placement:** the `EndTxn` always targeted r70 (the range of `id=1`,
  the *first* write), never r74 — the transaction record lives at the transaction's anchor
  key, not at an arbitrary or later-written location.
- **Topology caveat:** only 3 of the 5 "sending batch" events in this trial were genuine
  cross-node RPCs; the other 2 were local, same-process dispatch, purely because the
  gateway (n1) happened to coincide with r74's leaseholder. This is an artifact of which
  node was used as gateway and which ids were chosen, not a general property of multi-range
  transactions as such.

## Finding 2 — Single-range contrast: round-trip count does NOT distinguish the two
## conditions; batching does

Same procedure, using two ids confirmed to share a single range and leaseholder.

| | Multi-range trial | Single-range trial |
|---|---|---|
| Ranges touched | 2 | 1 |
| KV batches sent | 5 | 5 |
| Genuine cross-node RPCs | 3 (2 were local) | 5 (0 local — gateway ≠ this range's leaseholder) |
| Commit marker | `EndTxn(parallel commit)`, STAGING, int=2 ifw=2 | identical |
| 1PC / OnePhaseCommit | absent | **absent** |

The single-range trial, run with an explicit multi-statement `BEGIN`/`COMMIT`, produced the
**same batch count and the same parallel-commits/STAGING signature** as the multi-range
trial — no 1PC fired here either. This directly and empirically confirms a caveat the
working protocol states but which is easy to take on faith rather than verify: the 1PC fast
path requires single-range **and** single-batch; an interactive multi-statement
`BEGIN...COMMIT` does not qualify even on a single range.

## Interpretation

Round-trip / RPC count is confounded by gateway/leaseholder coincidence and does not, by
itself, distinguish single-range from multi-range transactions on this cluster — the
single-range trial actually had *more* genuine network RPCs than the multi-range one, for
reasons unrelated to the mechanism under test. The variable that actually separates 1PC
from parallel-commits is **batching** (single implicit statement vs. explicit
multi-statement), not range count in isolation. This distinction was subsequently isolated
and confirmed quantitatively in a following counter-based experiment.

## Corrections Applied

`async consensus` does not appear as literal trace text on this CockroachDB build; the
mechanism it names is present and demonstrable via timing analysis instead (the gap between
"proposing command" and "node sending response").

## Confidence

- Multi-range topology and parallel-commits/STAGING evidence: **High** (two independent
  trials, consistent, explicit trace text).
- Pipelining timing demonstration: **Medium-High** (one timestamped trial; internally
  consistent across both writes in that trial, but not independently repeated).
- Single-range / no-1PC contrast: **High** (unambiguous trace text, identical to the
  multi-range case).

## Caveats

- The local-vs-remote RPC split is specific to this cluster's gateway/leaseholder
  arrangement and would not generalize without re-verifying which node is used as gateway.
- Only one trial has timestamped timing data; the exact microsecond figures should be
  treated as indicative rather than final without a second timed repetition.

## Paper Hook

§3.2 (parallel commits, pipelining). The annotated trace excerpt and the single-vs-multi
range comparison table are both direct deliverables (Figure 2). Identifies batching, not
range count, as the variable that actually needs isolating — the setup for the following
counter-based experiment.
