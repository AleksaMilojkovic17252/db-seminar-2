---
## I2 -- Phantom read

- **Status:** `CONFIRMED`
- **Runs:** N=1 per level x 3 levels (deterministic given the mechanism, not timed --
  R4 doesn't apply)

### Hypothesis
Allowed at READ COMMITTED; prevented at REPEATABLE READ and SERIALIZABLE -- though the
REPEATABLE READ result specifically contradicts what the ANSI name would predict, since
CockroachDB's REPEATABLE READ is snapshot isolation, which prevents phantoms as a direct
side effect of pinning to one MVCC read timestamp, not because it targets phantoms
specifically.

### Raw output
See table above. All three trials verified via SHOW transaction_isolation, with B's own
INSERT output independently confirmed in every trial (not inferred from A's count alone).

### Interpretation
READ COMMITTED re-reads per statement, so B's committed insert became visible mid-
transaction -- count moved by exactly 1 (9999 -> 10000), matching the single row inserted.
REPEATABLE READ and SERIALIZABLE both held the count fixed at 10000 across B's insert --
snapshot isolation prevents phantoms as a structural consequence of pinning the whole
transaction to a single read timestamp, not via any predicate-locking mechanism. This is a
direct empirical illustration of Berenson et al.'s critique that ANSI's isolation-level
definitions don't match what real systems (including CockroachDB, and originally
PostgreSQL, from which the naming derives) actually implement -- ANSI REPEATABLE READ is
defined to permit phantoms; CockroachDB's REPEATABLE READ (snapshot isolation) does not.
Note also, as in I1: A's COMMIT succeeded cleanly at every level, including SERIALIZABLE --
I2 involves no write from A, so there is nothing for serializability's conflict-abort
machinery to reject, only something for the snapshot to hide.

### Caveats
The READ COMMITTED baseline count was 9999, not 10000, due to unrelated drift left over
from I1's SERIALIZABLE trial (id=1 at 5000.00, excluded from the > 9999 predicate); the
delta (+1) is what matters and is exact, but the absolute baseline number should not be
read as "10000 accounts all above 9999" without that context.

### Confidence
`High` across all three levels -- isolation proven via SHOW transaction_isolation, and B's
insert independently confirmed via its own output in every trial, not inferred.

### Paper hook
Sec 3.3, row 2 of the isolation-level anomaly table (Figure 4). Pairs directly with the
Berenson et al. / Adya discussion already flagged for I1 and I2's write-up -- worth citing
this REPEATABLE READ mismatch as the concrete example, not just an abstract claim.