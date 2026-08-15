# K7 — GLOBAL vs. REGIONAL Tables: Paying for Consistency in Milliseconds

## Goal
Make the clock-offset assumption tangible and measurable: a `LOCALITY GLOBAL` table
range is non-blocking for reads everywhere, paid for by writes that deliberately commit
at a *future* timestamp and wait out the interval. That interval's size is a function of
`--max-offset`. ⚠️ Uses a separate database (`mrtest`) so it doesn't disturb `seminar2`'s
range layout. ⚠️ Requires a full cluster restart for the second arm.

## Setup
```sql
CREATE DATABASE mrtest;
ALTER DATABASE mrtest SET PRIMARY REGION 'eu-west-1';
ALTER DATABASE mrtest ADD REGION 'us-east-1';
ALTER DATABASE mrtest ADD REGION 'us-west-1';
CREATE TABLE t_global   (id INT PRIMARY KEY, v STRING) LOCALITY GLOBAL;
CREATE TABLE t_regional (id INT PRIMARY KEY, v STRING) LOCALITY REGIONAL BY TABLE IN PRIMARY REGION;
```
100 rows seeded into each table. Region names matched the existing node localities
exactly, so no locality mismatches came up. Measurement used a purpose-built timing
script (not the full `harness.py`, which wasn't needed for a simple latency measurement
without concurrency/retry logic) — persistent connections, median/p95 over 100 single-row
operations per measurement.

## Arm 1 — `--max-offset=500ms` (baseline)

| Measurement | median | p95 |
|---|---|---|
| write t_global (n1) | 802.12ms | 803.41ms |
| write t_regional (n1) | 3.53ms | 4.95ms |
| read t_global (n2/n3) | 0.74 / 0.91ms | 1.34 / 1.39ms |
| read t_regional (n2/n3) | 1.15 / 1.16ms | 1.37 / 1.39ms |

Write penalty: **~800ms, ~227×** slower for `t_global`. Confirms "hundreds of ms slower."
Magnitude sits between `max_offset` alone (500ms) and `max_offset + propagation_slack`
(1500ms) — closer to the former.

Reads were a stronger result than "fast": `t_global` reads were directionally **faster**
than `t_regional` reads from both followers, consistent with `t_regional` needing an
actual leaseholder round trip to the primary region while `t_global` never does — a
small but consistent effect given near-zero loopback network cost either way.

## Arm 2 — `--max-offset=250ms` (all 3 nodes restarted)

| Measurement | median |
|---|---|
| write t_global (n1) | **401.01ms** |
| write t_regional (n1) | 3.47ms (unchanged) |

## The Full 2×2 (medians)

| | max-offset=500ms | max-offset=250ms |
|---|---|---|
| t_global write | 802.12ms | 401.01ms |
| t_regional write | 3.53ms | 3.47ms |

## Interpretation
The write penalty is cut almost exactly in **half**, matching the halving of `max_offset`
to within rounding. `t_regional` is unaffected in both arms, correctly serving as an
internal control. Solving `penalty = k × max_offset` for each arm gives **k ≈ 1.604 in
both**, an almost exact match — a clean **proportional** relationship, in direct contrast
to K5/K6's **additive** relationship between `target_duration` and the follower-read
threshold. Two different closed-timestamp-dependent mechanisms in the same system,
scaling with their respective parameters in genuinely different ways.

This is the direct, quantified version of Cockroach Labs' own documented recommendation
to lower `--max-offset` for multi-region clusters using global tables — these two arms
measure exactly how much that advice is worth on this hardware: roughly a 2× write-latency
reduction for a 2× tighter clock-offset assumption.

## Confidence
`High` — large N (100 per measurement) in both arms, clean and consistent proportional
relationship, `t_regional` correctly flat as an internal control.

## Paper Hook
§3.6 — likely the paper's headline number. The k≈1.6 constant and the proportional-vs-
additive contrast with K5/K6 are both worth their own sentence, not just the raw latency
table.
