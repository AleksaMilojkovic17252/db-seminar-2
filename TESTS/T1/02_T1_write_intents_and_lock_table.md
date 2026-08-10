# T1 — Write Intents and the Lock Table

## Goal and Original Hypothesis

**Goal:** make CockroachDB's provisional-write mechanism (the write intent) empirically
visible through `crdb_internal.cluster_locks`.

**Original hypothesis (as stated in the working protocol):** an uncommitted `UPDATE` leaves
a row in `crdb_internal.cluster_locks` identifying the holding transaction, the key, and the
lock strength; that row disappears once the transaction commits.

## Procedure, as actually executed

1. Session **[A]** (interactive terminal, gateway n1) ran `BEGIN;` then
   `UPDATE accounts SET balance = balance - 500 WHERE id = 1;`, left deliberately
   uncommitted.
2. Session **[M]** queried `crdb_internal.cluster_locks` for `table_name = 'accounts'`
   — returned 0 rows.
3. [A] committed. [M] re-queried — still 0 rows (expected, correctly committed by that
   point).

The first pass returned 0 rows both before and after commit, which on its face looked like
a straightforward refutation. Before accepting that, three procedural (non-CockroachDB)
explanations were checked and ruled out in sequence, rather than assumed:

- **Client-side autocommit.** Considered because a GUI SQL client had been used for
  session [A]. Confirmed and ruled out in two steps: first, indirect evidence from the
  account balance (`10000.00 → 9000.00` after two runs, consistent only with each run
  committing immediately rather than staying open); then, on retry through a real
  interactive terminal, direct confirmation via the full session transcript —
  `BEGIN` returned `BEGIN`, `UPDATE ...` returned `UPDATE 1`, and the session was
  genuinely parked at an open prompt.
- **Wrong node queried.** [M]'s first queries went through n1 and n3; the intent
  physically lives wherever the range's leaseholder is (id=1 is on the range whose
  leaseholder is n2, per the range-topology check). Querying n2 directly still returned
  0 rows for the uncontended intent, ruling this out as the explanation too.
- **Timing.** Re-confirmed [A] was still genuinely open at the exact moment each
  check ran, via terminal transcripts and repeated live queries rather than a single
  snapshot.

With all three ruled out, the 0-rows result was treated as a real finding, and the
experiment was extended — structurally now equivalent to a write-write conflict scenario
— by issuing a second `UPDATE` against the same key (`id=1`) while [A] stayed open.

## Finding 1 — An uncontended write intent is invisible in `crdb_internal.cluster_locks`

Repeated queries against a confirmed-open, confirmed-correctly-placed transaction, run from
all three nodes, consistently returned 0 rows. This directly refutes the protocol's literal
hypothesis that any uncommitted write leaves a queryable row in this view.

## Finding 2 — A contended lock produces rows for both sides simultaneously

Once a second `UPDATE` targeted the same key while [A] was still open,
`crdb_internal.cluster_locks` (queried from n2, the leaseholder for this key) returned:

| txn_id | lock_strength | granted | contended | duration |
|---|---|---|---|---|
| f0ffe85e… (original holder, [A]) | Intent | true | true | 9.911364s |
| 27cd62bd… (new, blocked writer) | Exclusive | false | true | 9.911352s |

**Interpretation:** `crdb_internal.cluster_locks` is not a general inventory of every write
intent — it is populated specifically by the contention/wait-queue mechanism. A held intent
becomes visible in this view only once a second transaction actually collides with it, at
which point both the holder and the waiter appear together in the same query result. This
reframes, rather than simply negates, the original hypothesis: write-intent enforcement
itself is real and continuous (the second write genuinely blocked), but this particular
introspection view is a window into active contention, not a standing inventory of
provisional writes.

**Secondary observations:**
- The `duration` field appears to measure time spent in a *contended* state, continuously
  growing, rather than a fixed value captured once. Two independent measurements of the
  same wait support this: the lock-table snapshot mid-wait read `duration: 9.911352s` /
  `9.911364s` for the two sides; the blocked writer's `UPDATE` itself did not actually
  return until **193.014 seconds** of real wall-clock time had elapsed before [A] finally
  committed. Both readings are consistent with a live "time waited so far" counter rather
  than a value fixed at the moment the wait began.
- The granted, non-waiting transaction reports `lock_strength = Intent`; the blocked,
  pending one reports `Exclusive` — despite both being plain `UPDATE` statements, neither
  using `SELECT ... FOR UPDATE`. This looks like a granted-vs-pending distinction, separate
  from the plain-intent-vs-`FOR UPDATE` distinction the protocol document describes
  elsewhere, and is not something the source protocol addresses directly — worth treating
  as an original observation from this cluster, not a restated claim from the document.

## Closeout

Full lifecycle confirmed end to end: [A]'s `COMMIT` returned cleanly (`COMMIT`); the
previously-blocked second `UPDATE` returned `UPDATE 1` after 193.014s; the invariant
baseline was restored afterward (`sum(balance) = 100000000.00`, confirmed).

## What remains open

Whether `crdb_internal.cluster_locks` fans out cluster-wide *during contention* was not
independently re-tested from n1 or n3 — the contended-state row was only ever observed by
querying n2, which also happens to be the leaseholder for this key. The uncontended-state
check (0 rows) was confirmed from all three nodes, but that only demonstrates "nothing to
show," not "the view fans out." This is the one genuinely unresolved question from this
experiment; everything else reached a confirmed conclusion.

## Methodological note (relevant to the paper's methodology / threats-to-validity section)

This experiment surfaced an operational requirement, not a CockroachDB property: any
session that needs to hold a transaction open across multiple manual steps must run in a
genuine interactive terminal session, not a GUI database client — a GUI client may
autocommit each statement or route sequential statements to different pooled connections,
silently defeating a manually-held-open transaction with no error raised. This applies to
every later multi-statement `BEGIN...COMMIT` block in the protocol.

## Confidence

- Finding 1 (uncontended invisibility): **High** — confirmed across all 3 nodes, with three
  alternative procedural explanations directly ruled out first, not assumed.
- Finding 2 (contention triggers dual visibility): **Medium-High** — clean single trial,
  mechanism is plausible and internally consistent, but not yet independently repeated.
- The duration-measures-contention-time reading: **Medium-High** — corroborated by two
  independent measurements of the same wait, ~190 seconds apart, both consistent with a
  live counter. The Intent-vs-Exclusive granted/pending distinction remains
  **Low-Medium** — still a single data point, worth confirming when the write-write
  conflict experiment is run formally.

## Paper hook

Write intents / lock table mechanism section. Arguably a more precise and more interesting
claim than the source protocol's own framing — worth presenting as "`cluster_locks` is a
contention window, not an intent inventory" rather than simply restating the document's
original hypothesis as confirmed fact.
