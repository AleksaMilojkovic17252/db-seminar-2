# K3 + K4 — MVCC Timestamp Order, Causal Reverse, and the Fix

## Goal
K3 and K4 are run as one connected sequence — K4 has no independent setup and depends
directly on K3's exact final state. Together they form what the working protocol calls
"the intellectual core of the consistency chapter": K3 demonstrates the *mechanism*
(MVCC timestamp order diverging from real-time/story order for concurrent transactions);
K4 demonstrates the *observable consequence* (a historical read that violates the
application's own causal model); a third piece demonstrates the *fix* (a foreign key
closing the anomaly). An honest framing is stated up front and carried through the
write-up: this is not a strict-serializability violation, since the two transactions
involved are genuinely concurrent — it's the mechanism causal reverse rides on, not a
correctness bug.

## K3 — MVCC Timestamp Order ≠ Real-Time Order

**Hypothesis:** transaction [A] (which will insert the *parent* comment, `id=1`) starts
first — its `BEGIN` and initial read both precede [B]'s insert of the *reply* (`id=2`,
`parent_id=1`). But because a third session [M]'s intervening read leaves a
timestamp-cache entry that [A]'s eventual write collides with, [A]'s write is forced to a
timestamp *above* both [M]'s read and [B]'s already-committed write — meaning the parent
should end up with a **higher** MVCC timestamp than the child, despite representing the
logically "earlier" thing in the story.

**Procedure:** [A] begins, reads `comments WHERE id=1` (empty), holds open. [B] inserts
the reply (commits immediately). [M] reads `id=1` again (still empty, but now leaves a
timestamp-cache marker). [A] then inserts the parent and commits. [M] finally reads both
rows' `crdb_internal_mvcc_timestamp`.

**Result:** clean, first-try success, no retry needed.
| id | parent_id | crdb_internal_mvcc_timestamp |
|---|---|---|
| 1 (parent) | NULL | 1784749942842655159.0000000002 |
| 2 (child) | 1 | 1784749925020041481.0000000000 |

Gap: **~17.8 seconds**, parent later than child — substantial, not marginal.

**Interpretation:** confirms the timestamp-push mechanism directly. A's own read fixed an
initial timestamp; M's later read of the same still-empty key left a timestamp-cache entry
above B's commit; A's subsequent write collided with that entry and was pushed above it.
Because A is SERIALIZABLE, it performed a read refresh before committing at the forwarded
timestamp — nothing else had written key 1 in the interval, so the refresh succeeded
silently.

## K4 — A Historical Read That Sees the Child Without the Parent

**Hypothesis:** a read `AS OF SYSTEM TIME` strictly between the two comments' MVCC
timestamps returns the child without the parent.

**Procedure (continuing directly from K3's state, no reset):**
```sql
SELECT * FROM comments AS OF SYSTEM TIME '1784749930000000000.0000000000' ORDER BY id;
```

**Result:** exactly one row — `id=2, parent_id=1, "OP is wrong"`. Row 1 absent.

**Interpretation:** confirms causal reverse as an *observable* phenomenon, not just the
underlying mechanism. A query at a real, valid historical timestamp returns data that is
locally inconsistent with the application's own causal model — a reply referencing a
parent that, as of that same instant, had not yet been written. This matters beyond a
party trick: `BACKUP` uses `AS OF SYSTEM TIME` internally, so a backup taken at an unlucky
moment can capture this exact child-without-parent state as a durable, restorable
artifact, not a transient read anomaly that self-corrects.

## The Fix — comments_fk with a Real Foreign Key

**Hypothesis:** adding a real FK on `parent_id` makes the child insert depend on reading
the parent row, closing the independence the anomaly requires.

**Procedure:** created `comments_fk` with `parent_id INT NULL REFERENCES comments_fk(id)`,
re-ran K3's identical recipe against it.

**Result:** B's very first `INSERT` — the reply, referencing a parent that doesn't exist
yet — failed immediately:
```
ERROR: insert on table "comments_fk" violates foreign key constraint
"comments_fk_parent_id_fkey", SQLSTATE 23503
```

**Interpretation:** confirms the theoretical point via the strongest possible mechanism —
outright rejection at insert time, before any concurrency or timestamp-ordering question
is even reached. Worth being precise: this is mechanistically **different** from what K3
tested. K3 exercises serializability's conflict-detection machinery; the fix demonstration
exercises a plain referential-integrity check, the same one that would fire even in a
single-threaded context. Both support the same theoretical conclusion (a real dependency
forecloses the anomaly) via genuinely different enforcement paths — worth not conflating
the two mechanisms in the write-up.

## Confidence
`High` throughout all three parts — every step produced a clean, single-trial,
unambiguous result with no retries or ambiguity to resolve.

## Paper Hook
§3.5, likely the strongest single exhibit in the whole project: mechanism (K3) directly
producing an observable consequence (K4), with a concrete real-world stakes argument
(BACKUP) and a demonstrated fix, all in one connected sequence.
