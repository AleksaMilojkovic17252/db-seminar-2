# K5 — Follower Reads and the Staleness Threshold

## Goal and Hypothesis
Find the minimum staleness (`AS OF SYSTEM TIME '-Ns'`) at which a follower node will
actually serve a read, and connect that number to the closed-timestamp mechanism.
Latency is explicitly not the right metric here — on loopback there's no WAN round trip
to save, so a follower read isn't faster than a leaseholder read on this hardware; the
`follower_reads.success_count` metric (note: no `kv.` prefix, per an earlier PRE-5
correction) is the real signal. **Hypothesis:** `staleness=0` never triggers a follower
read; the threshold sits somewhere near `kv.closed_timestamp.target_duration` (3s) plus
some propagation margin.

## Procedure
A Python script swept 9 staleness values (`0` through `10s`), running 50 reads at each
against a follower node for `id=9000` (confirmed on a range led by a different node), and
snapshotting `follower_reads.success_count` before/after each bucket.

## Results

| staleness | delta follower_reads |
|---|---|
| 0 – 4s | 0 (flat) |
| 5s, 10s | 50 (every read) |

A sharp, binary threshold — nothing fractional in between — between **4s and 5s**.

**Prediction check:** `staleness=0` → 0 confirmed exactly. The threshold prediction was
only *partially* confirmed: the real threshold is meaningfully higher than a naive
`target_duration`-only estimate (~3.2s) would suggest — a real, unexplained-at-the-time
gap, later revisited in K6.

## Follow-Up Checks
- **All three supported staleness forms** (`follower_read_timestamp()`,
  `with_max_staleness('10s')`, `with_max_staleness('10s', true)`) executed cleanly,
  ~2ms each.
- **`EXPLAIN VERBOSE` did not confirm a follower read** — the plan output (`distribution:
  local`, a plain scan) contained no marker either way. Logged honestly as inconclusive by
  this method, not treated as a confirmation.
- **Bounded staleness + a JOIN** produced a real but narrower-than-expected restriction:
  `unimplemented: cannot use bounded staleness for LOOKUP JOIN` (SQLSTATE `0A000`,
  referencing tracked issue 67562) — specific to the lookup-join strategy the planner
  chose for that particular query, not a blanket "joins aren't allowed" restriction.

## Interpretation
`staleness=0` confirmed exactly. The threshold itself sits meaningfully above the naive
prediction, in a sharp, deterministic transition rather than a gradual one. The gap
between predicted (~3.2s) and observed (>4s) threshold was left as an open question at
this point in the project — later resolved (see K6) as evidence of an additive margin on
top of `target_duration`, once a second data point at a different setting became
available.

## Confidence
`High` for the threshold bracket and the LOOKUP JOIN restriction's exact text. `Low` at
the time of this experiment on *why* the gap between predicted and observed threshold
exists.

## Paper Hook
§3.5/3.6. The sharp 0→50 transition and the precise LOOKUP JOIN restriction text are both
strong, quotable exhibits. Pairs directly with K6 for the full threshold-tuning story.
