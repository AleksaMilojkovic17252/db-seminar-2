# P2 — SERIALIZABLE vs. READ COMMITTED vs. RC+FOR UPDATE (The Centerpiece)

## Goal and Hypotheses
Quantify, simultaneously, what weaker isolation buys (throughput) and what it costs
(correctness) — most write-ups measure only the first half, producing the true but
useless conclusion "READ COMMITTED is faster." Workload: a read-modify-write bank
transfer (read both balances, compute new values in the client, write them back) — the
cross-statement window is what makes lost updates possible; a single-statement update
would not discriminate between isolation levels at all (per I4). Deliberately narrow hot
key space (`--accounts 50`, not 10,000) so contention is real, not diluted away.
Deterministic lock ordering (lower id first) so C2-style deadlocks don't confound the
retry statistics.

| # | Prediction | Refuted if |
|---|---|---|
| H1 | SERIALIZABLE: money_delta = 0, high restart activity | money is lost |
| H2 | READ COMMITTED: money_delta ≠ 0 — money is destroyed — with far fewer retries and higher throughput | the invariant holds |
| H3 | RC + FOR UPDATE: money_delta = 0, throughput between the other two | it loses money |
| H4 | RC + FOR UPDATE may be **slower** than SERIALIZABLE, since it takes exclusive locks where serializability needed none | it beats SERIALIZABLE |

## Procedure — Building the Tooling
This experiment required building the project's reusable measurement harness
(`harness.py`) for the first time — persistent per-thread connections, `perf_counter`
timing around the transaction only, and explicit accounting of every outcome
(commit/retry/retry-exhausted/error), specifically to avoid the disqualifying failure
mode of a `cockroach sql -e` loop (process-spawn overhead dominating the measurement, and
silenced errors making an all-failing run look like the fastest one).

**Two real bugs were found and fixed before trusting any data, not after:**
1. The harness's own stated contract (§4.3) makes `isolation_verified` mandatory in every
   result, or the run is `INCONCLUSIVE` — but the reference `p2.py` script never actually
   surfaced it in its output. Fixed by adding an explicit canary check in `main()`.
2. `conn_for()`'s isolation-verification check itself was silently broken: since
   `psycopg2` implicitly begins a transaction on a connection's first statement, and that
   first statement was `SET default_transaction_isolation`, the `SET` ran *inside* the
   very transaction it was trying to configure — meaning it only ever affected the *next*
   transaction, never the one it verified. This passed silently for the SERIALIZABLE arm
   only because SERIALIZABLE happened to already be the cluster's true prior default,
   masking the bug; it surfaced immediately and correctly as a `FATAL` on the READ
   COMMITTED arm, which genuinely differed from the default. Fixed by committing the
   priming transaction before the verification check, so the check runs in a genuinely
   fresh transaction. The already-collected SERIALIZABLE data was discarded and re-run
   rather than kept on the reasoning that it was "probably still correct" — its
   verification, even if the underlying data was likely fine, hadn't actually proven
   anything.

## First Pass (N=1 per arm) — a Cautionary Result, Not the Final One
| Arm | Throughput (txn/s) | p50/p95/p99 (ms) | Retries | Money delta |
|---|---|---|---|---|
| SERIALIZABLE | 336.7 | 20.24/144.83/376.87 | 489 (writetooold) | 0.00 |
| READ COMMITTED | 417.8 | 28.96/93.10/131.08 | 0 | 50.00 |
| RC + FOR UPDATE | 353.0 | 34.77/104.95/140.25 | 0 | 0.00 |

H1–H3 confirmed cleanly at N=1. H1's restart mechanism was a precise correction to the
hypothesis's own wording: all restarts were `txn.restarts.writetooold` (I4's write-write
collision mechanism), not `txn.restarts.serializable` (I3's read-set-staleness
mechanism) — under real contention, direct write collisions dominate. **H4 did not
resolve at N=1**: RC+FOR UPDATE actually *won* on throughput and p95, contradicting the
hypothesis's literal prediction — flagged explicitly as too close and too small a sample
to trust, rather than reported as a refutation.

## Full Protocol — 5× Repeat + Concurrency Sweep
21 total runs (5 repeats × 3 arms at conc=16, plus 3 arms × conc∈{4,64}), each with a
reset in between, run via a second orchestrator script.

**H1: robustly confirmed — `money_delta = 0.00` in all 7 runs**, no exceptions.

**H2: confirmed, revised to a sharper claim.** Money delta was never zero across any of
the 7 runs, but the *sign* genuinely flipped: `-10.00, 240.00, 300.00, 450.00, -230.00`
(repeats), `-290.00` (conc=4), `160.00` (conc=64). Mechanistic explanation: this
bidirectional-transfer workload can lose either side of a transfer (debit or credit)
depending on which of two racing writes lands last, so a lost update can equally *create*
or *destroy* money. The revised, sharper claim: READ COMMITTED does not conserve money in
either direction — a stronger statement than "destroys money."

**H3: robustly confirmed — `money_delta = 0.00` in all 7 runs**, no exceptions.

**H4: resolves clearly only at N=5+, and the reversal from N=1 is itself worth reporting
as a methodological finding.** At conc=16 medians, SERIALIZABLE now wins throughput
(236.4 vs. 161.2), p50 (27.66 vs. 45.12ms), and p95 (257.34 vs. 339.19ms) — only p99
still favors RC+FOR UPDATE. The N=1 pilot had the opposite result on two of these four
metrics purely from run-to-run noise.

**The concurrency sweep sharpens H4 into an unambiguous, dramatic result:**

| conc | SERIALIZABLE (txn/s) | READ COMMITTED (txn/s) | RC + FOR UPDATE (txn/s) |
|---|---|---|---|
| 4 | 156.3 | 205.2 | 157.7 |
| 16 (median) | 236.4 | 290.3 | 161.2 |
| 64 | 217.9 | 306.6 | **78.4** |

At `conc=64`, RC+FOR UPDATE's throughput **collapses to 78.4 txn/s** (worse than its own
`conc=4` figure), with p50 exploding to 552.41ms — a 7× gap against SERIALIZABLE's 77.58ms
at the identical concurrency — and wall-clock time nearly tripling for the same 2000
transactions. SERIALIZABLE also degrades under this load (3 transactions hit
`retry_exhausted`; p99 reaches 3.1s) but far more gracefully, staying roughly flat in
throughput. This directly and sharply reproduces Cockroach Labs' own ACIDRain claim that
overusing `FOR UPDATE` under READ COMMITTED can perform worse than SERIALIZABLE.

## Interpretation
All four hypotheses confirmed, two (H2, H4) in a more precise or more dramatic form than
originally stated. H4's N=1-vs-N=5 reversal is a genuine, citable illustration of why the
protocol's minimum-N rule (R4) exists — not a footnote, a result in its own right.

## Confidence
`High` for all four hypotheses at full N. H4 specifically should be reported with the
N=1-vs-N=5 reversal noted explicitly.

## Caveats
`retry_exhausted=3` for SERIALIZABLE at `conc=64` — those transactions never committed and
were safely rolled back (`money_delta` remained 0.00), an availability cost distinct from
a correctness failure.

## Paper Hook
§4 — likely the two central figures of the entire paper: the isolation-level comparison
table at conc=16, and the concurrency-sweep collapse of RC+FOR UPDATE. H2's
zero-retries-zero-errors-yet-money-vanished result and H4's N=1-vs-N=5 reversal are both
individually strong enough for their own paragraphs in Methods.
