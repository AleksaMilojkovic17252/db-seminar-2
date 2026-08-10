# Setup & Data Seeding — Distributed Transactions & Consistency in CockroachDB v24.3.0

Source material for the seminar paper's Environment / Methodology sections. Compiled from
the PRE and SETUP phases of the experiment protocol, as actually executed and verified
against a live 3-node cluster (not assumed from documentation).

## 1. Environment

- **CockroachDB version:** v24.3.0 CCL (x86_64-pc-linux-gnu, built 2024/11/21), confirmed via `SELECT version()`
- **Cluster ID:** 27e5aa93-4956-48bd-bf63-4d512ec33c25
- **Organization:** Elektronski Fakultet
- **Topology:** 3 nodes, single machine, loopback, `--insecure`, replication factor 3 (default)
- **Localities:** n1 `localhost:26257` region=eu-west-1,zone=a · n2 `localhost:26258` region=us-east-1,zone=b · n3 `localhost:26259` region=us-west-1,zone=c
- **Host machine:** CachyOS (Arch-based) x86_64, Linux kernel 7.1.3, Intel Core i5-1235U (4P+8E cores) @ 4.40GHz, 31.08 GiB RAM, btrfs filesystem
- **--max-offset:** 500ms, identical on all nodes
- **Database:** `seminar2`

## 2. License and Isolation Gates

- **License:** confirmed set — `enterprise.license` non-empty, `cluster.organization` = "Elektronski Fakultet". Cluster is not in the 7-day grace/throttle window; READ COMMITTED, REPEATABLE READ, follower reads, and multi-region features are not licensing-gated.
- **Isolation-level gates:** `sql.txn.read_committed_isolation.enabled = true`, `sql.txn.repeatable_read_isolation.enabled = true` — both confirmed **proven**, not just set, via `SHOW transaction_isolation` inside actually-opened transactions:

| Requested | Reported |
|---|---|
| READ COMMITTED | `read committed` |
| REPEATABLE READ | `repeatable read` (this build reports the literal name, not "snapshot") |
| SERIALIZABLE | `serializable` |

No silent upgrade at either weaker level. This licenses trusting isolation-level experiments
on this cluster — provided each individual experiment still checks `SHOW transaction_isolation`
for itself; this cluster-level proof does not exempt later spot-checks.

## 3. Baseline Cluster Settings

| Setting | Value | Relevance |
|---|---|---|
| kv.closed_timestamp.target_duration | 3s | baseline for the follower-read staleness sweep; later changed to 500ms for comparison |
| kv.closed_timestamp.side_transport_interval | 200ms | follower-read threshold experiments |
| kv.closed_timestamp.follower_reads.enabled | true | required for follower reads to function at all |
| kv.range_merge.queue.enabled | false | prevents manual range splits (Section 6) from being undone in the background |
| kv.transaction.parallel_commits.enabled | true | required for multi-range commit tracing |
| kv.transaction.write_pipelining.enabled | true | required for pipelining to appear in traces |
| kv.rangefeed.enabled | false | unexplained; flagged as a watch item if follower-read experiments underperform |

## 4. Schema

Five tables, each purpose-built for a specific class of later experiment:

- **`accounts(id, owner, balance, region, updated_at)`** — bank-transfer correctness oracle
  for the throughput-vs-correctness centerpiece experiment. Deliberately has **no
  `CHECK (balance >= 0)`**: a CHECK constraint would mask a lost-update anomaly by
  rejecting the write that destroys money, and the entire point of that later experiment
  is to make the anomaly observable, not prevented.
- **`inventory(product_id, name, stock, version)`** — write-write conflict / deadlock target.
- **`counters(id, name, value)`** — single hot key for pure contention experiments.
- **`doctors(id, name, on_call)`** — write-skew scenario.
- **`comments(id, parent_id, body)`** — causal-order / MVCC-timestamp-ordering scenario.
  `parent_id` is deliberately **not** a foreign key: an FK would force the child insert to
  read the parent row, which would make the two transactions conflict, which would make
  serializability forbid exactly the timestamp reordering that scenario exists to
  demonstrate.

## 5. Seed Data and Row-Count Rationale

| Table | Rows |
|---|---|
| accounts | 10,000 |
| inventory | 1,000 |
| counters | 1 |
| doctors | 2 |
| comments | 0 (populated by later experiments themselves) |

**Invariant baseline:** `sum(balance) = 100,000,000.00` across 10,000 accounts, confirmed
and re-confirmed after every reset. This is the correctness oracle every later mutation of
`accounts` is checked against.

**Why the seed data was not scaled up to millions of rows (methodology / scope note):**
this project's subject is transaction and consistency *mechanism*, not throughput at data
volume, and three considerations argued against a larger dataset:
1. Multi-range distribution needed for later experiments comes from explicit manual range
   splits, not from row count — 10,000 narrow rows are only a few MB, nowhere near the
   default 512 MiB range size, so "natural" splitting would require tens of millions of
   rows landing at unpredictable, non-reproducible boundaries instead of the exact ids
   needed.
2. The isolation-level throughput/correctness comparison is *actively harmed* by more
   accounts: it deliberately narrows the hot key space to a small fixed set, because a
   large, evenly-spread account pool drives contention toward zero and makes every
   isolation level look identical — defeating the comparison's purpose.
3. This scale (10,000 rows, ~5 ranges) is an accepted, disclosed limitation to state
   honestly in a Threats-to-Validity discussion, not a gap to close by seeding more.

## 6. Range Topology

Manual splits: `accounts` at (2001, 4001, 6001, 8001); `comments` at (2). Both followed by
`SCATTER` to distribute leaseholders.

**Verified topology — `accounts` (5 ranges):**

| Range | Key range | Leaseholder |
|---|---|---|
| 70 | TableMin – 2001 | n2 |
| 71 | 2001 – 4001 | n2 |
| 72 | 4001 – 6001 | n1 |
| 73 | 6001 – 8001 | n1 |
| 74 | 8001 – (shared boundary, see below) | n1 |

- id=1 → range 70 → **n2**
- id=9000 → range 74 → **n1**
- Different leaseholders confirmed for these two ids — the structural prerequisite for
  every later "distributed transaction" claim.

**`comments` (2 ranges):** the range starting at id=2 is its own, empty range (leaseholder
n1). The other side of the split — ids < 2 — turned out to be the **same physical range as
`accounts`'s highest-id range**, since no split was made at that table boundary. Row-count
arithmetic on that shared range (3003 = 2000 accounts rows + 1003) strongly suggests
`inventory` (1000 rows), `doctors` (2 rows), and `counters` (1 row) are also co-located in
it — inferred from arithmetic, not yet directly confirmed by querying those tables
individually.

**Caveat:** lease distribution across the 5 accounts ranges is uneven — n3 holds none of
them. Worth rechecking before any experiment that specifically needs a leaseholder other
than n2.

## 7. Version-Drift Corrections Applied

Three settings/queries in the working protocol document did not match this exact build and
were corrected during setup — each is a small, citable methodology finding in its own right,
consistent with the general expectation that column/setting names drift across versions:

| Written in protocol | Actual on this cluster | Note |
|---|---|---|
| `kv.range_merge.queue_enabled` | `kv.range_merge.queue.enabled` (dot, not underscore) | old name still works as a deprecated alias, prints a NOTICE only |
| `SELECT name, value FROM [SHOW CLUSTER SETTINGS] WHERE name = ...` | `SELECT variable, value FROM crdb_internal.cluster_settings WHERE variable = ...` | column is `variable`, not `name`; `SHOW CLUSTER SETTINGS`'s own column name was not independently re-tested |
| `kv.follower_reads.success_count` | `follower_reads.success_count` (no `kv.` prefix) | needed for the follower-read experiments |

Also confirmed directly: `crdb_internal.cluster_transactions` has no `status` column (it
lives on `crdb_internal.cluster_sessions` instead) — a known trap the protocol document
predicted by name and this cluster reproduced exactly. `crdb_internal.node_metrics` keys on
`store_id`, not `node_id` (functionally equivalent in this topology, one store per node, but
the column name differs).

## 8. Operational Setup

Idempotent start/stop scripts were used: a start script wipes and bootstraps
(`cockroach init`) only on a genuinely fresh data directory, and resumes without touching
existing data on every subsequent run; a stop script sends a graceful SIGTERM
(`pkill -f "cockroach start"`), not a hard kill. A reset script (restore `accounts` balances
to 10000.00, `doctors.on_call` to true, `counters.value` to 0, `inventory` to
stock=100/version=1, clear `comments`) is run between experiments to restore the invariant
baseline before each new one begins.
