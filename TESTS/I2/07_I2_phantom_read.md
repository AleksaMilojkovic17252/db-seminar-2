# I2 — Phantom Read

## Goal and Hypothesis
Same three-level structure as I1, but with a predicate (`COUNT(*) WHERE balance > 9999`)
instead of a single row, and an `INSERT` instead of an `UPDATE` as the interfering write.
**Hypothesis:** allowed at READ COMMITTED; prevented at REPEATABLE READ and SERIALIZABLE —
flagged in advance as a genuinely interesting case, since ANSI's REPEATABLE READ is
*defined* to permit phantoms, while CockroachDB's REPEATABLE READ is snapshot isolation
under a borrowed name, which behaves differently.

## Procedure
Same [A]/[B] shape as I1: [A] opens a transaction at the level under test, proves
isolation, counts rows matching the predicate. [B] inserts one new row that matches it
(`id=99999, balance=99999`). [A] counts again and commits. The inserted row is deleted
afterward regardless of outcome, to avoid contaminating later experiments.

One loose end surfaced during the READ COMMITTED trial: the transcript showed both counts
and B's insert, but not [A]'s own `COMMIT` — rather than assume it had been run, the
session was checked directly and the `COMMIT` output confirmed explicitly before moving
on, the same standard applied throughout this phase.

## Results

| Isolation level | 1st count | 2nd count | Anomaly (phantom)? |
|---|---|---|---|
| READ COMMITTED | 9999 | 10000 | **Yes** |
| REPEATABLE READ | 10000 | 10000 | No — prevented |
| SERIALIZABLE | 10000 | 10000 | No — prevented |

The READ COMMITTED baseline was 9999, not 10000, due to unrelated drift left over from an
earlier I1 trial (`id=1` sitting at `5000.00`, excluded from the `>9999` predicate) — the
delta (+1) is what matters and is exact; the absolute baseline number on its own would be
misleading without that context.

## Interpretation
READ COMMITTED re-reads per statement, so B's committed insert became visible mid-
transaction — count moved by exactly 1, matching the single row inserted. REPEATABLE READ
and SERIALIZABLE both held the count fixed across B's insert. This is the interesting
part: CockroachDB's REPEATABLE READ prevents phantoms not because it targets phantoms
specifically, but as a structural side effect of pinning the whole transaction to one
MVCC read timestamp — there is no later statement-level re-read to notice the new row.
This is a direct, concrete illustration of the well-known critique (Berenson et al.) that
ANSI's isolation-level definitions don't actually describe what real systems (including
CockroachDB, and the PostgreSQL naming convention it borrows) implement: ANSI REPEATABLE
READ is defined to *permit* phantoms; this system's REPEATABLE READ does not.

As in I1, A's `COMMIT` succeeded cleanly at every level — I2 involves no write from A
either, so again there is nothing for serializability's abort machinery to reject.

## Confidence
`High` across all three levels — isolation proven via `SHOW transaction_isolation`, and
B's insert independently confirmed via its own output at every level.

## Paper Hook
§3.3, row 2 of the isolation-level anomaly table. Pairs directly with I1 as the
"REPEATABLE READ prevents phantoms" concrete exhibit for the Berenson et al. discussion.
