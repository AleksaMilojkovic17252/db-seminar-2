# I5 — SELECT ... FOR UPDATE and FOR SHARE

## Goal and Hypothesis
Show that READ COMMITTED can be made safe against I4's lost-update anomaly via explicit
row locking, and that the two lock strengths (`FOR UPDATE`, `FOR SHARE`) behave
differently — while directly checking, not assuming, two specific claims from the working
protocol about how those locks would appear in `crdb_internal.cluster_locks`.

## Part 1 — FOR UPDATE

**Hypothesis:** replacing I4's plain `SELECT` with `SELECT ... FOR UPDATE` makes a
concurrent writer block until the reader's transaction commits, eliminating the lost
update — and the protocol additionally predicted this lock would appear as *unreplicated*
`Exclusive`, contrasted against T1's *replicated* `Intent`.

**Procedure:** [A] opens READ COMMITTED, reads `counters.value FOR UPDATE`. [B] attempts
`UPDATE counters SET value = 5` and is expected to block. A third session [M] inspects
`cluster_locks` while [B] is blocked. [A] then writes and commits, releasing the lock.

**Result:** [B] blocked for **34.771s**, then completed after [A]'s commit — final value
`5`, i.e. both writes landed in a well-defined order, nothing lost. Functional hypothesis
**confirmed**. But the lock table showed both rows as `Replicated`, not `Unreplicated` as
predicted — a direct, evidenced correction to the working protocol, especially notable
since every lock observed anywhere in this project (T1's granted/blocked rows, both I5
trials) has shown `Replicated`, never once `Unreplicated`. The comparison that *does*
hold: `lock_strength = Exclusive` for the FOR UPDATE grant, vs. T1's `Intent` for an
ordinary uncontested write — a real, useful strength distinction, just not the durability
one predicted.

## Part 2 — FOR SHARE

**Hypothesis (as stated in the working protocol):** a `FOR SHARE` lock should **not**
block a concurrent writer's exclusive acquisition.

**Procedure:** identical shape, `FOR SHARE` in place of `FOR UPDATE`.

**Result:** [B]'s write **blocked for 62.621s** — directly refuting the stated hypothesis.
The lock table confirmed why: A held `Shared/Replicated/granted=true`; B's queued write
showed `Exclusive/Replicated/granted=false`. A Shared lock blocked a concurrent Exclusive
request.

**Why this refutation is probably correct, not just a build quirk:** standard
shared/exclusive lock semantics predict exactly this — the entire point of a shared lock
is to exclude conflicting exclusive acquisitions while permitting other shared holders.
A blocked writer is the textbook behavior of that model, not an anomaly to explain away.
The protocol's original claim reads as a genuine error rather than something that changed
between versions.

## Combined Findings
- **Durability has read `Replicated` in every lock row observed in this entire project**
  (T1, FOR UPDATE, FOR SHARE — 4 rows across 2 different lock strengths and 2 different
  acquisition mechanisms). `Unreplicated` was never observed.
- **Three distinct `lock_strength` values** confirmed across the project: `Intent`
  (ordinary uncontested write, T1), `Exclusive` (`FOR UPDATE`), `Shared` (`FOR SHARE`).

## Confidence
`High` for both parts — isolation proven, blocking directly timed (substantial durations,
not timing flukes), lock strengths and durability directly observed via `cluster_locks`
rather than inferred.

## Paper Hook
§3.3/3.4 (RC-plus-locking as a lost-update mitigation, and its cost). Two direct
refutations of specific documented claims in one experiment — the durability correction
and the FOR SHARE blocking behavior — both worth their own sentences rather than folding
into a single "mostly worked as expected" summary.
