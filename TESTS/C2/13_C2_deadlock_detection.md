# C2 — Deadlock Detection

## Goal and Hypothesis
Force a genuine cross-node deadlock cycle and confirm the cluster detects and breaks it
automatically rather than stalling permanently. **Hypothesis:** the cycle (A holds
`id=1`/wants `id=9000`; B holds `id=9000`/wants `id=1`) results in exactly one transaction
aborted per trial, with the error explicitly naming a deadlock/push mechanism. `id=1` and
`id=9000` sit on different ranges with different leaseholders (confirmed in SETUP-3),
making this a genuinely distributed cycle, not an incidental same-node one. Distribution
of which side loses was deliberately left unpredicted.

## Procedure
Two real terminal sessions, [A] and [B], run in a precise interleaved order: [A] writes
`id=1`; [B] writes `id=9000`; [A] attempts to write `id=9000` (blocks, closing the cycle);
[B] attempts to write `id=1` (the second half of the cycle). Repeated 5 times (R4's
minimum for a distribution claim), with a reset between each trial.

## Results

| Trial | Loser | Reason code |
|---|---|---|
| 1 | A | ABORT_REASON_PUSHER_ABORTED |
| 2 | B | ABORT_REASON_PUSHER_ABORTED |
| 3 | B | (same signature, reported as outcome-only) |
| 4 | A | (same signature, reported as outcome-only) |
| 5 | A | (same signature, reported as outcome-only) |

**A lost 3/5, B lost 2/5.**

Trials 1–2 captured full verbatim transcripts; trials 3–5 were reported as win/loss only,
a deliberate proportionality decision once the underlying error mechanism was already
independently confirmed twice — a difference in evidentiary depth across the 5 trials,
noted explicitly rather than left implicit.

## Interpretation
Deadlock detection is reliable across all 5 trials — no stalls, no undetected cycles.
Trial 1's write-up initially described `ABORT_REASON_PUSHER_ABORTED` as identifying "the
pusher," implying a structural asymmetry; trial 2 immediately corrected this — both sides
of a genuine cycle are symmetrically pushing against each other's held lock by definition,
so the reason code confirms a push-based resolution occurred, not which side was
structurally selected. A 3/2 split at N=5 is consistent with anything from a true 50/50
distribution to a mild real skew — this sample size cannot distinguish between those, and
the result is reported as "not clearly skewed, not confirmed as exactly even" rather than
forced into either conclusion.

## Confidence
`High` for detection reliability (5/5, no stalls). `Low-Medium` for characterizing the
win/loss distribution — genuinely underdetermined at this sample size.

## Caveats
Trials 3–5 differ in evidentiary depth from trials 1–2 (outcome-only vs. full verbatim
transcripts) — a deliberate choice once the mechanism was independently confirmed twice,
not an oversight, but worth noting for anyone weighing the strength of the distribution
claim specifically.

## Paper Hook
§3.4. The alternating-loser pattern across just 5 trials is a compact illustration of
"not deterministic, don't assume a fixed loser" — consider a simple dot/bar plot of the 5
outcomes as a minor figure.
