# K1 — No Stale Reads Across Gateways

## Goal and Hypothesis
Establish the positive consistency guarantee before looking for the one gap in it later
in the phase: a read that starts *after* a write commits will always observe that write,
regardless of which node serves the read. **Hypothesis:** `stale_reads: 0` across a large
number of write/read cycles split across different gateways. A non-zero count would
actually be a serious bug, not an interesting finding — worth double-checking the
methodology rather than believing it, if it ever occurred.

## Procedure
A Python/psycopg2 script (this phase's first use of a real script rather than manual
terminal steps, since it's a 1000-iteration load test): write `counters.value` on n1,
then immediately read it on both n2 and n3, comparing each read against the just-written
value. 1000 iterations, 2000 total reads.

## Result
```json
{"iterations": 1000, "reads": 2000, "stale_reads": 0}
```
Zero stale reads, no violations printed (the script prints a line per violation, and
printed none).

## Interpretation
Confirms the guarantee cleanly. One honest limitation flagged before the result came back,
not after: on a single machine, the writer and every reader share one physical clock. This
confirms the *mechanism* — reads route to the leaseholder, the single serialization point
for that range — but it cannot, on its own, distinguish "CockroachDB guarantees this" from
"there was no clock skew available on this hardware to expose a violation."

## Confidence
`High` for the specific claim tested on this hardware. The single-machine caveat is
reported honestly as a scope limitation, not resolved by this experiment.

## Paper Hook
§2.1/3.5. Establishes the baseline the rest of phase K (especially K2, K8, K9) builds on
or probes the edges of.
