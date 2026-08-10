# T3 — One-Phase Commit vs. Parallel Commits (Counter-Based)

## Goal and Hypothesis

**Goal:** quantify, via exact metric counters rather than latency (justified for the same
reason as the previous experiment — loopback RTT is too close to zero to be meaningful),
whether a transaction takes the 1PC fast path or the parallel-commits path, and confirm
that this is governed by two independent conditions — single range AND single batch —
rather than either alone.

**Hypothesis, refined using the prior tracing experiment's result as a starting point:** of
the four combinations of {single-range, multi-range} × {implicit single-statement, explicit
`BEGIN`/`COMMIT`}, only the single-range + implicit combination should show
`Δtxn.commits1PC`; all three other combinations should show `Δtxn.parallelcommits` instead.

## Methodological Detour: Background Noise (a citable finding in its own right)

The first measurement attempt failed cleanly rather than ambiguously: 20 transactions were
run, but the cluster-wide `Δtxn.commits` came back at **10,455** — roughly 500× the expected
signal. This was diagnosed rather than assumed: an independent cross-check (comparing
`txn.commits` read at two points separated only by a reset script and a read-only query,
with no experimental transactions run at all) showed the count still climbing by 262 with
zero transactions of our own executed — confirming continuous background commit activity on
the cluster, independent of the experiment. Most likely candidates are CockroachDB's own
background jobs (automatic table statistics collection, SQL stats flushing, or the jobs
scheduler's periodic poll), though the specific source was not conclusively confirmed.

**Fix:** the problem was time-window length, not sample size. The original method took
snapshots and ran the loop across multiple manual, human-paced round trips (minutes of real
time); background commits accumulate across that entire window regardless of what's being
measured. The fix was procedural, not statistical: before/loop/after run as a single
uninterrupted shell script with no manual steps in between, minimizing the window during
which background noise can accumulate. This dropped background noise from 10,455 to under
100 per arm — not zero, but small enough for a ~20-transaction signal to be clearly visible
against it.

## Preliminary Discovery: `node_metrics` is confirmed node-local

`SELECT store_id, name, value FROM crdb_internal.node_metrics WHERE name = 'txn.commits';`
returned **one row**, not three — confirming, rather than assuming, that this view is
node-local. Every snapshot in this experiment was therefore taken from all three nodes'
ports and manually summed, rather than trusting a single gateway's view.

## Results — All Four Arms

| Arm | Form | Range | Δcommits | Δcommits1PC | Δparallelcommits | Per-node pattern |
|---|---|---|---|---|---|---|
| (a) | implicit, single statement | single | 73 | **29** | 0 | 1PC: n1 +23, n2 +3, n3 +3 (gateway-concentrated, some noise) |
| (b) | explicit BEGIN/COMMIT | single | 86 | 7 | **20** | parallel: n1 +20, n2 +0, n3 +0 (exact) |
| (c) | implicit, single statement | multi | 70 | 3 | **20** | parallel: n1 +20, n2 +0, n3 +0 (exact) |
| (d) | explicit BEGIN/COMMIT | multi | 106 | 8 | **23** | parallel: n1 +23, n2 +0, n3 +0 (gateway-concentrated, close to the 20 signal) |

All four arms used the tightened single-script method; N=20 transactions each. Arm (d) was
run in a later session than (a)-(c) (cluster/session counters had reset to much smaller
absolute values by then — e.g. n1's baseline `txn.commits` was ~2,700 rather than ~123,000),
so its noise floor is not directly comparable to the others in absolute terms. Since only
the *delta* over the tightened window is used, this does not bias the measurement, but it
means the four rows are not one contiguous run.

Arm (d) is now counter-measured directly, corroborating rather than merely being carried
forward from the T2 trace evidence: `Δparallelcommits = 23` against a signal of 20, entirely
attributed to the gateway node (n1: +23, n2/n3: +0), matching the exact-attribution pattern
seen in arms (b) and (c). `Δcommits1PC = 8` and the unattributed remainder of `Δcommits`
(106 − 23 − 8 = 75) are consistent with the same background-noise source discussed above,
not with any 1PC activity in this arm.

**The 2×2, complete:**

| | Single-range | Multi-range |
|---|---|---|
| **Implicit (single batch)** | (a) **1PC** | (c) **parallel-commits** |
| **Explicit BEGIN/COMMIT** | (b) **parallel-commits** | (d) **parallel-commits** (counter-measured, corroborated by trace-level evidence from T2) |

## Interpretation

Only one of the four combinations — single-range AND single-batch — takes the 1PC fast
path. Every other combination, whether batching alone changes (a→b), range count alone
changes (a→c), or both change (a→d), lands on parallel-commits. Arms (a) and (c) hold
batching constant (both implicit/single-statement) and vary only range count, isolating
range count as independently sufficient to block 1PC; arms (a) and (b) hold range count
constant and vary only batching, isolating batching the same way. This is a stronger and
more precise claim than "multi-range transactions can't use 1PC" — it demonstrates two
independent necessary conditions rather than one, with each isolated by its own controlled
comparison rather than inferred from a single observation.

Arm (d) is now backed by both kinds of evidence: the prior tracing experiment produced
direct, textual, twice-repeated trace evidence (`EndTxn(parallel commit)` appearing verbatim
in two independent trials), and the counter delta measured here (`Δparallelcommits = 23`,
entirely attributed to the gateway node) independently confirms the same conclusion. The two
evidence types agree, which is itself worth noting: neither was redundant with the other —
the trace shows the *mechanism* firing on a single transaction, the counter shows it firing
consistently across 20.

## Confidence

- Arms (b) and (c): **High** — exact per-node attribution (+20/0/0 on the relevant metric
  in both cases), minimal ambiguity.
- Arm (a): **High**, with a noted caveat — its background-noise contribution is
  proportionally larger than in (b) or (c) (roughly 6 of 29 attributable to noise by
  comparison with the other arms' flat per-node baseline), though the gateway-node
  concentration pattern (+23 of 29 on the node that ran the loop) still supports the
  attribution.
- Arm (d): **High** — now counter-measured (not merely qualitative), with the same
  gateway-concentrated attribution pattern as (b) and (c) (+23 of 23 parallel-commits on n1),
  and independently corroborated by the T2 trace evidence.

## Caveats

- Background commit activity, while greatly reduced by the tightened method, was never
  fully eliminated (on the order of 70–106 total commits per arm, cluster-wide, against a
  signal of 20). The exact source was not conclusively identified.
- Arm (a)'s attribution is the least clean of the four counter-measured arms, though still
  well above the noise floor and corroborated by the per-node concentration pattern.
- Arm (d) was measured in a separate session from (a)-(c), after the cluster's metric
  counters had reset to much smaller absolute values (background-job accumulation resumed
  from a lower baseline). This does not affect the delta-based measurement but means the
  four rows are not one contiguous, back-to-back run.

## Paper Hook

§3.2, Figure 3 (Δcommits1PC vs. Δparallelcommits × 4 transaction forms) — the headline
table for this section. The background-noise methodology detour is itself worth a paragraph
in the Methods or Threats-to-Validity section: counter-based measurement on a live,
non-isolated cluster requires tight time-windowing between snapshot and measurement, not
just a larger replicate count.
