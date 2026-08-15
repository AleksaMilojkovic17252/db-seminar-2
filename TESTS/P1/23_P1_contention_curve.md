# P1 — The Contention Curve

## Goal and Hypothesis
Show throughput as a function of concurrency at multiple levels of key-space contention,
using `cockroach workload run kv` (the benchmarking tool built into the `cockroach`
binary) rather than a custom script or shell loop. `--cycle-length` is the contention
dial — the number of distinct keys the workload writes to; `cycle-length=1` means every
operation hits the same single key. **Hypothesis:** the `cycle-length=100000` line scales
up with concurrency; the `cycle-length=1` line flattens or degrades, since a single key is
a single Raft group with a single leaseholder that no amount of concurrency can
parallelize.

## Procedure
Flag names were confirmed via `cockroach workload run kv --help` before committing to a
run, per the standing "discover, don't assume" discipline — all needed flags
(`--concurrency`, `--cycle-length`, `--read-percent`, `--duration`, `--ramp`,
`--display-every`) existed exactly as expected. `workload init kv` (no database specified
in its connection string) created its own table in a database named `kv` — its own
default, not `defaultdb`, confirmed rather than assumed. A short pilot run validated the
output format before committing to the full sweep: 4 cycle-lengths × 7 concurrency levels
= 28 combinations, each 60s measured + 10s discarded ramp, run via a Python orchestrator
(not manual, given the scale) that captured each run's full raw output to its own log
file, snapshotted `txn.restarts.*` before/after every combination (summed across all 3
nodes, `node_metrics` being confirmed node-local), and wrote results incrementally so a
crash wouldn't lose progress. A separate parser script extracted the final cumulative
summary line from each of the 28 logs into one compact table.

## Results — Throughput (ops/sec)

| cycle-length | conc=1 | conc=4 | conc=16 | conc=64 |
|---|---|---|---|---|
| 100000 | 241.1 | 859.3 | 2815.9 | **4707.6** |
| 100 | 228.2 | 881.2 | 2909.8 | **4661.4** |
| 10 | 242.5 | 940.5 | 1988.1 | **1929.9** |
| 1 | 294.6 | 259.2 | 252.7 | **249.6** |

`cycle=100000` and `cycle=100` are nearly identical curves, both scaling smoothly through
64 concurrent workers. `cycle=10` scales normally up to `conc=8`, then hard-flattens
between `conc=16` and `conc=32` and degrades slightly at `conc=64` — visible saturation at
a moderate contention level, not only the extreme. `cycle=1` never moves from ~250–295
ops/sec at any concurrency, and is actually *highest* at `conc=1` — adding workers past
the first doesn't just fail to help, it makes things marginally worse. Meanwhile p50
latency at `cycle=1` rises from 3.3ms to 251.7ms across the same range — a ~76× increase
in wait time for zero throughput gain.

## The Restart-Counter Sub-Investigation
All 28 arms showed **completely empty** `txn.restarts.*` deltas — including the highest-
contention arms, which was surprising enough to investigate rather than accept at face
value. Two competing explanations: a genuine finding (single-key contention resolves via
blocking/queuing, not retries — consistent with C1's earlier direct demonstration) versus
a broken snapshot mechanism. A direct sanity check against a known ground truth (K8's
diagnostic script, which had independently produced 5 confirmed
`ReadWithinUncertaintyIntervalError` events) found the true cluster-wide count to be
**10**, not 5 — confirming the counter/query mechanism works correctly in general (the
extra 5 are attributable to K8's *original* 100-attempt script, whose errors were likely
silently absorbed via transparent server-side retry, per K8's own leading theory —
independent corroborating evidence for that finding, found for an unrelated reason). This
validated P1's all-zero result as genuine: a single hot key under equal-priority
contention resolves entirely through blocking, paying its cost purely in latency, not in
wasted, retried work.

## Interpretation
Confirms the hypothesis, with more precision than a binary "flat vs. scaling" split:
contention effects appear at a threshold (visible starting around `cycle=10`, absent at
`cycle=100+`), not only at the single-key extreme, and the cost of contention shows up as
latency, not throughput waste — directly consistent with the (validated) zero-restart
finding.

## Confidence
`High` for the throughput/concurrency shape — large N per point (14,000–280,000 ops per
measurement), clean and consistent pattern across all 4 cycle-lengths. `High` for the
restart-mechanism validity, once cross-checked against known ground truth.

## Paper Hook
§3.6, headline figure — a 4-line ops/sec-vs-concurrency plot, one line per cycle-length.
The `cycle=1` latency-vs-throughput contrast (flat throughput, 76× latency increase) is a
strong standalone exhibit even without the restart-counter story.
