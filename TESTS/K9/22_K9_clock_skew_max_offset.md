# K9 — Clock Skew and --max-offset: An Honest Negative Result

## Goal
Determine whether the `--max-offset` safety mechanism can actually be exercised on this
topology. The protocol's own expected answer going in is no — the value of this
experiment is recording precisely *why*, as Threats-to-Validity material, not a shrug.

## Step 1 — Baseline Offset (Confirmed)
```sql
SELECT store_id, name, value FROM crdb_internal.node_metrics
WHERE name LIKE 'clock-offset%';
```
Cross-validated against the DB Console's Runtime → Clock Offset graph (screenshot taken).
Both sources agree: all three nodes stayed under **~75 microseconds** across roughly an
hour of observation — a ratio of about **1:6,600** against the 500ms threshold.
Unsurprising given all three processes read the same kernel's `CLOCK_REALTIME`, but
useful as a clean, cross-validated baseline.

## Step 2 — Why Fault Injection Isn't Available Here (Documented, Not Independently Tested)
Cited from the working protocol rather than independently tried on this cluster:

| Approach | Why it fails |
|---|---|
| `date -s` / `timedatectl` | Moves the host clock — all three nodes move together, relative offset stays 0 |
| `libfaketime` / `LD_PRELOAD` | Go reads the clock via the vDSO, bypassing libc — the hook never fires |
| Linux time namespaces | Virtualize `CLOCK_MONOTONIC`/`CLOCK_BOOTTIME` only, not `CLOCK_REALTIME` |
| Docker containers | Share the host kernel's clock; `CAP_SYS_TIME` would move the host, i.e. all nodes at once |

Reported honestly with lower confidence than the directly-tested steps, since none of
these were actually attempted on this cluster.

## Step 3 — A Mismatched Fourth Node (Refutes the Protocol's Own Expectation)
A fourth node was started with `--max-offset=250ms` against a cluster running `500ms`
elsewhere. The protocol's own text anticipated this "may be refused." **Result: it
joined successfully** — `crdb_internal.gossip_nodes` showed a 4th live row, and the full
startup log showed zero lines matching `offset`/`refus`/`mismatch`/`fatal` across several
minutes of normal operation. The mismatch was accepted, not blocked — a direct,
evidenced refutation of the documented expectation. What this does *not* establish:
whether the mismatch causes any subtler correctness effect short of an outright
rejection — genuinely untested here, reported as an open question rather than implied
resolved.

**Two side-findings surfaced during cleanup, both worth keeping:**
- `cockroach node decommission` failed twice with identical allocation errors — node4
  shared a region (`eu-west-1`) with n1, and `mrtest`'s region-voter constraints left no
  valid target for 2 replicas once decommission needed to consolidate them. Resolved via
  direct process kill + store removal rather than forcing a clean decommission, since
  `mrtest` was disposable. A genuine, separate finding: adding a node into an
  already-represented region creates real rebalancing complications for region-
  constrained tables, independent of the max-offset question.
- A real bug was found in the K8 scripts during invariant verification: session B's
  autocommit `UPDATE` persists regardless of whether session A's transaction under test
  succeeds or fails. All 5 of K8's final diagnostic attempts raised
  `ReadWithinUncertaintyIntervalError` on A, yet B's writes all landed anyway, producing a
  small (`100000000.10`) invariant drift, caught and reset before continuing. Worth citing
  as a concrete reason reset discipline must apply between every script run, not just
  between named experiments.

## Step 4 — Real Skew via a Second Machine (Not Attempted)
No VM or second machine was available for this project. Reported honestly as unverified
rather than simulated: the documented behavior (an offending node terminates itself) is
cited from Cockroach Labs' documentation, not independently confirmed here.

## Interpretation
K9 delivers exactly what was predicted on the core skew question — a negative result,
for four separable and specific reasons (Step 2) — but Step 3 overturned the expectation
for a closely related, adjacent claim. The honest framing for the paper: clock skew
itself could not be induced on a single machine, but the one adjacent claim that *could*
be tested — whether a topology-mismatched node gets rejected at join time — turned out to
be false on this build, directly contradicting the documentation's own hedge.

## Confidence
`High` for Steps 1 and 3 (direct, unambiguous, cross-validated where possible). Step 2:
inherited confidence from the source document, not independently earned. Step 4: not
applicable — explicitly unverified, not estimated.

## Paper Hook
Threats to Validity, and §3.5. Step 3's refutation is the standout exhibit — pairs
naturally with I5's `FOR SHARE` refutation as a recurring theme: specific, checkable
claims in secondary sources that this project's methodology caught being wrong, not just
claims it happened to confirm.
