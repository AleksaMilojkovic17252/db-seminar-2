# P3 — Client-Side Retry Strategies Compared

## Goal and Hypothesis
Turn the mandatory `40001` retry loop from a code listing into an actual measurement.
Using P2's transfer workload at deliberately higher contention (`--accounts 20 --conc
32`), compare four retry strategies that differ only in the sleep between attempts: no
retry at all, immediate retry (no sleep), fixed 0.05s sleep, and exponential backoff with
jitter (the harness default). **Hypothesis:** immediate retry produces a genuine retry
storm — total attempts explode and p99 degrades — while exponential backoff with jitter
converges cleanly.

## Step 1 — `force_retry` Unit-Test Check: Not Reproducible Here
`SELECT crdb_internal.force_retry('500ms')` — a documented unit-test convenience that
fabricates a retryable error on demand, explicitly not a load test — hung indefinitely.
Ruled out systematically before giving up on it: tried in a plain terminal instead of the
GUI client (still hung), and after a full computer restart with cluster health confirmed
live and healthy beforehand (still hung). Logged `NOT-REPRODUCIBLE-HERE` and skipped
deliberately, since this step is a convenience check that doesn't feed into the actual
measurement — worth a one-line mention in Threats to Validity as an unexplained anomaly,
not silently omitted.

## Step 2 — The Real Comparison
A dedicated script (reusing the harness's connection-verification fix directly, since it
needed a parameterizable sleep function the shared `harness.py` doesn't expose) ran all
2000 transactions per strategy, with a reset between each.

## Raw Results

| Strategy | success_rate | reported attempts/commit | total_attempts | p50/p95/p99 (ms) |
|---|---|---|---|---|
| none | 0.3815 | 2.621 | 2000 | 29.31/80.34/170.29 |
| immediate | 0.9125 | 2.664 | 4862 | 22.95/487.26/1437.91 |
| fixed | 0.9265 | 2.287 | 4238 | 23.36/449.61/2151.02 |
| exponential_jitter | 0.9965 | 1.788 | 3563 | 40.66/1073.99/3583.77 |

**On its face, this looks like a direct refutation:** p99 gets monotonically *worse*, not
better, from `none` through `exponential_jitter` — the literal opposite of "backoff
converges."

## A Necessary Correction Before Interpreting Anything
The reported `attempts/commit` figure divides *total* attempts (including attempts spent
on transactions that ultimately failed) by successful commits — a real number, but not
what "attempts per commit" implies. Since a `retry_exhausted` outcome always uses exactly
`max_retries` attempts (a guarantee of the loop's own logic, not an estimate), the true
figure can be backed out exactly:

| Strategy | commits | retry_exhausted | attempts on failures | attempts on successes | **true attempts/success** |
|---|---|---|---|---|---|
| none | 763 | 1237 | 1237 | 763 | 1.000 (no retries permitted) |
| immediate | 1825 | 175 | 1750 | 3112 | **1.705** |
| fixed | 1853 | 147 | 1470 | 2768 | **1.494** |
| exponential_jitter | 1993 | 7 | 70 | 3493 | **1.753** |

Corrected, `exponential_jitter`'s apparent efficiency largely evaporates — it needs a
similar number of tries per success as `immediate`, and only looked more efficient because
it has almost no failures to dilute the average with.

## Explaining the p99 Result — Survivorship Bias, Not a Refuted Mechanism
Percentiles are computed only over *committed* transactions, and each strategy's set of
survivors is fundamentally different: `none`'s survivors are disproportionately the *easy*
transactions that never hit real contention (explaining its excellent p99); `exponential_
jitter`'s survivors include nearly every hard case the other strategies simply abandoned,
and successfully fighting through heavy contention costs real wall-clock time — which
shows up as *that strategy's own* tail latency. Comparing p99 across strategies with
radically different success rates (38% to 99.65%) isn't a like-for-like comparison.

**What does compare fairly across strategies: total database-side load** (`total_attempts`
is an exact count, unaffected by which transactions succeeded). `immediate` (4862)
generates more total load than `fixed` (4238) or `exponential_jitter` (3563), for a worse
success rate than either — directly supporting the "hammers the database" half of the
original hypothesis, even though the p99 half of it does not hold as literally stated.

## Interpretation
The hypothesis is refuted as literally worded (exponential+jitter has the *worst*
committed-transaction p99, not the best), but the underlying practical conclusion is
supported once success rate and total load are weighed alongside latency rather than
looking at p99 in isolation: `none` fails outright on 62% of attempts (pushing the retry
problem back onto the caller, not solving it); `immediate` generates the most database
load for a worse outcome than more patient strategies; `exponential_jitter` achieves
near-total success (99.65%) at the *lowest* total load of the three real-retry strategies,
paying for it in success-rate-weighted latency among the (mostly hard-fought) transactions
that do succeed — a real cost, just not the one the raw p99 number appears to show.

## Confidence
`High` for the corrected attempts/success and total-load figures (exact arithmetic).
`High` for the refutation of the literal p99-convergence claim. `Medium` for the overall
practical conclusion (exponential+jitter is still the best strategy in practice) — well
supported by the reasoning above but not independently re-verified with a fairer,
population-matched comparison method.

## Caveats
The measurement script does not write per-transaction data the way P2's does, so the
attempts/success correction relies on `retry_exhausted`'s deterministic attempt count
rather than raw row-level data — solid for this specific correction, a real limitation for
any finer-grained analysis. N=1 per strategy, not independently repeated.

## Paper Hook
§4/Methods. The p99-survivorship-bias finding is worth its own paragraph — a concrete,
demonstrated example of why naive latency percentiles can mislead when comparing
strategies with different success rates, a point with relevance beyond this specific
experiment.
