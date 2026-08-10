---
## I4 -- Lost update

- **Status:** `CONFIRMED`
- **Runs:** N=1 per level x 3 levels

### Hypothesis
READ COMMITTED permits the lost update; SERIALIZABLE rejects it via 40001. REPEATABLE
READ's behavior was left an open question per the protocol, to be reported whichever way
it fell rather than assumed.

### Raw output
See table above. READ COMMITTED: both UPDATEs succeeded, B's committed value (5) silently
overwritten by A's stale-informed write (1) -- no error. REPEATABLE READ and SERIALIZABLE:
A's UPDATE itself (not COMMIT) raised WriteTooOldError, SQLSTATE 40001, in both cases;
final value 5 (B's write) intact in both.

### Interpretation
Confirms the two-statement (read, decide, write) shape is required to observe this anomaly
at all -- distinguished explicitly from I1's non-repeatable read, which is a similar
two-statement shape but where A's READ silently changes, versus here where A's WRITE
silently destroys B's committed write based on stale information. REPEATABLE READ falls
on the same side as SERIALIZABLE for this anomaly, not READ COMMITTED -- consistent with
both being snapshot-based (REPEATABLE READ is snapshot isolation under the ANSI name,
confirmed directly this trial via the error's own metadata showing iso=Snapshot).
Mechanistically distinct from I3: this anomaly is caught immediately at the conflicting
WRITE via a direct write-write timestamp collision (WriteTooOldError), not deferred to
COMMIT via a read-set staleness check (RETRY_SERIALIZABLE, as in I3) -- two different
detection mechanisms defending against two different anomalies, both surfacing under the
same 40001 SQLSTATE.

### Caveats
As with I1/I2, both retry-rejection trials showed the ROLLBACK-on-already-aborted-COMMIT
behavior -- expected client behavior once a statement inside a transaction errors, not
itself part of the finding.

### Confidence
`High` across all three levels -- error text captured verbatim in both rejection cases,
B's write independently confirmed via its own output in every trial, and the final value
checked explicitly rather than inferred.

### Paper hook
Sec 3.3, row 4 of the isolation-level anomaly table (Figure 4). The iso=Snapshot detail in
the REPEATABLE READ error metadata is a strong, quotable, literal confirmation of "REPEATABLE
READ is snapshot isolation" -- worth using as a direct exhibit rather than just asserting it.