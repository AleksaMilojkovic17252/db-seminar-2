# K6 — Moving the Threshold: Closed-Timestamp Tuning

## Goal and Hypothesis
Directly follow up on K5's unexplained gap: does the follower-read staleness threshold
move in proportion to `kv.closed_timestamp.target_duration`? ⚠️ This experiment changes a
cluster-wide setting and requires restoring it afterward.

## Procedure
```sql
SET CLUSTER SETTING kv.closed_timestamp.target_duration = '500ms';
```
Waited ~30s for propagation, then re-ran K5's identical sweep script unmodified against
the new setting, then restored the setting to its original value.

## Results
Threshold at `target_duration=500ms`: strictly between **1s and 2s** (same sharp,
binary 0→50 transition pattern as K5). K5's threshold at `target_duration=3s` was
between 4s and 5s.

## Interpretation
Direction confirmed: lowering `target_duration` lowered the threshold. But the magnitude
does **not** scale proportionally, and the arithmetic is worth showing rather than just
asserting:
- `target_duration` dropped 6× (3s → 500ms).
- The threshold only dropped roughly 3× (midpoint ~4.5s → ~1.5s).

A pure proportional model would predict a K6 threshold around 0.5–0.83s; the observed
1–2s bracket sits clearly above that. A better-fitting model, worth stating as a
refinement rather than a proven formula given the coarse bracketing available: an
**additive** margin on top of `target_duration` (`threshold ≈ target_duration + C`).
Solving each trial's bracket for `C`:
- K5 (target=3s, threshold ∈ (4,5]) → C ∈ (1, 2]
- K6 (target=500ms, threshold ∈ (1,2]) → C ∈ (0.5, 1.5]
- Overlap consistent with both: **C ≈ 1–1.5s**

This isn't just "higher than predicted, twice" — it's the *same* roughly-constant extra
margin appearing at two different settings, which is a real pattern, not two unrelated
surprises. (A later experiment, K7, surfaced a specific candidate for this constant:
`kv.closed_timestamp.propagation_slack = 1s`, seen for the first time in K7's settings
dump — consistent with, though not independently proven to be, the source of this
margin.)

## Confidence
`Medium` — the additive model is a good fit to only 2 coarsely-bracketed data points; a
finer sweep at both settings (e.g. half-second increments near each threshold) would be
needed to confirm `C` is genuinely constant rather than coincidentally consistent across
just these two brackets.

## Caveats
The cluster setting was restored to `3s` after this trial — any later experiment assuming
the original PRE-6 baseline should confirm restoration completed, not just assume it.

## Paper Hook
§3.5/3.6, present alongside K5 as one figure (two threshold curves), with the additive-
margin model as the analytical takeaway rather than two isolated numbers. The
`propagation_slack` connection (K7) is worth a forward-reference.
