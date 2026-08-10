---
## I1 -- Non-repeatable read

- **Status:** `CONFIRMED`
- **Runs:** N=1 per level x 3 levels (anomaly presence/absence is deterministic given
  the mechanism, not a timed measurement -- R4 doesn't apply)

### Hypothesis
Allowed at READ COMMITTED; prevented at REPEATABLE READ and SERIALIZABLE.

### Raw output
See table above. All three trials independently verified via SHOW transaction_isolation
(proof, not assumption) and, for the two later trials, B's own UPDATE output confirmed
directly rather than inferred.

### Interpretation
READ COMMITTED takes a fresh read per statement, so B's committed write became visible
mid-transaction to A -- the anomaly. REPEATABLE READ and SERIALIZABLE pin the whole
transaction to a single MVCC snapshot; B's write is simply invisible to A, not blocked.
Mechanistically: A's first read leaves an entry in the timestamp cache, forcing B's write
to take a timestamp above A's read timestamp -- B is not held up by A, the two writes are
just ordered such that A's snapshot predates B's commit. A's COMMIT succeeded without error
at every level, including SERIALIZABLE, since I1 involves no write from A -- there is
nothing for serializability to reject, only something for the snapshot to hide.

### Confidence
`High` across all three levels -- isolation proven via SHOW transaction_isolation at each,
and B's write independently confirmed via its own output in the REPEATABLE READ and
SERIALIZABLE trials (READ COMMITTED's result was self-evident from A seeing B's exact value).

### Caveats
The READ COMMITTED trial did not separately capture B's own terminal output -- not
strictly needed there, since A's second read showing B's specific value (5000.00) is
itself sufficient proof B ran, but noted for consistency with the other two trials.

### Paper hook
Sec 3.3, row 1 of the isolation-level anomaly table (Figure 4).