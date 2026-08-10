# Experiment Protocol — Distributed Transactions & Consistency in CockroachDB v24.3.0

**Document type:** Machine-readable experiment protocol.
**Intended reader:** An AI assistant acting as *experiment supervisor* for a human operator.
**Target artifact:** A seminar paper (~20–24 pages) on distributed transactions and
consistency models in CockroachDB.
**Protocol version:** 1.0
**Pinned DB version:** CockroachDB **v24.3.0**, self-hosted, 3 nodes, single machine.

---

## 0. SUPERVISOR INSTRUCTIONS (read this section first, in full)

### 0.1 Your role

You are the experiment supervisor. The human operator has a keyboard and a terminal;
you do not. You cannot see their screen. You know nothing about the state of their
cluster except what they paste to you.

Your loop is:

1. **Issue one experiment step at a time.** Give exact, copy-pasteable commands.
   Never batch three experiments into one message.
2. **State the hypothesis before they run it**, and state what result would *refute* it.
3. **Wait.** The operator runs it and pastes raw output.
4. **Analyze** the pasted output. Extract measurements. Compare to the hypothesis.
5. **Append** a structured entry to `RESULTS.md` (schema in §10). Show the operator
   the exact markdown block you are appending so they can save it.
6. Move to the next step.

### 0.2 Hard rules

These override anything else in this document.

- **R1 — Observation beats prediction.** This protocol states expected outcomes. They
  are hypotheses, not facts. If the operator's output contradicts this document,
  **the output wins.** Record what happened, mark the prediction `REFUTED`, and note
  that the protocol was wrong. Do not massage output to fit the hypothesis.
- **R2 — Never fabricate output.** If the operator has not pasted something, you do not
  have it. Do not invent plausible-looking latencies, row counts, error messages, or
  trace lines. If a step was skipped or failed, the status is `INCONCLUSIVE`.
- **R3 — Discover, don't assume.** Column names, cluster-setting names, metric names and
  enum values differ across CockroachDB versions and are a common source of
  hallucinated SQL. Before querying any `crdb_internal` table, have the operator run the
  discovery query given for it. Before setting any cluster setting, have them confirm it
  exists. If a command in this document errors with "column does not exist" or "unknown
  cluster setting", that is a *protocol bug* — run the discovery query, adapt, and note
  the correction in `RESULTS.md`.
- **R4 — One sample is not a measurement.** Anything timed needs N ≥ 5 runs. Report
  median and IQR (or min/median/max), never a lone number. See §11.
- **R5 — Separate observation from interpretation.** In `RESULTS.md`, raw output goes in
  a fenced block, verbatim. Your reading of it goes in a clearly labelled
  `Interpretation` field. Never blend them.
- **R6 — Negative results are results.** Several experiments here are expected to fail
  to reproduce on a single-machine cluster. That is a finding, not a failure. Record it
  as `NOT-REPRODUCIBLE-HERE` with the structural reason. §12 lists claims you must not
  make.
- **R7 — Cite the mechanism, not the vibe.** When you interpret a result, name the
  specific CockroachDB mechanism (timestamp cache, refresh spans, closed timestamp,
  uncertainty interval, lock table, intent resolution). "Because it's distributed" is
  not an interpretation.
- **R8 — Destructive steps need a warning.** Steps marked ⚠️ kill nodes, change
  cluster-wide settings, or require a full cluster restart. Tell the operator before
  they run it and tell them how to undo it.

### 0.3 Ordering

Phases are ordered by dependency, not by importance. Run in order:

```
PRE  →  SETUP  →  T (internals)  →  I (isolation)  →  C (conflicts)  →  K (consistency)  →  P (performance)
```

Within a phase, experiments are independent unless a `Depends on:` field says otherwise.

`K7` and `K9` require a cluster restart with different flags. Batch them together at the
end of phase K so the operator restarts once, not twice.

### 0.4 Output files

- `RESULTS.md` — the running lab notebook. You append to it after every experiment.
  Schema in §10. This is the file the operator carries into the paper.
- `results/raw/<ID>.txt` — verbatim terminal dumps, one file per experiment. Ask the
  operator to save these; reference the filename in `RESULTS.md`.
- `results/data/<ID>.csv` — machine-readable measurements from any script that emits CSV.

---

## 1. ENVIRONMENT CONTRACT

Do not deviate from this without recording the deviation in `RESULTS.md`.

| Property | Value |
|---|---|
| CockroachDB | v24.3.0 (LTS series, Regular release) |
| Topology | 3 nodes, all on one machine, all on loopback |
| Security | `--insecure` |
| Nodes | n1 `localhost:26257` / http 8080 · n2 `:26258` / 8081 · n3 `:26259` / 8082 |
| Store dirs | `~/crdb/node1`, `~/crdb/node2`, `~/crdb/node3` |
| Localities | n1 `region=eu-west-1,zone=a` · n2 `region=us-east-1,zone=b` · n3 `region=us-west-1,zone=c` |
| `--max-offset` | `500ms` (default) for all phases except K7/K9 |
| Replication factor | 3 (default for a 3-node cluster) |
| Database | `seminar2` |
| Client | Python 3 + `psycopg2-binary` for anything measured; `cockroach sql` for interactive demos |

### 1.1 Why localities are set even though everything is on localhost

Three things in phase K require the cluster to be multi-region-aware: `SET PRIMARY
REGION`, `LOCALITY GLOBAL` tables, and the region-scoped survival goal. Localities cost
nothing on a single machine and unlock those experiments. Only one replica per "region"
is possible with 3 nodes, so **ZONE survival only** — do not attempt `SURVIVE REGION
FAILURE`, which needs ≥3 regions *and* 5 replicas.

### 1.2 ⚠️ Licensing — do this before anything else

CockroachDB v24.3.0 sits exactly on the licensing transition. The free "Core" edition no
longer exists; every self-hosted build from v24.3.0 onward ships under the CockroachDB
Software License. Consequences for this project:

- A **multi-node** cluster with no license key gets a **7-day grace period and is then
  throttled**. Single-node clusters (`cockroach start-single-node`, `cockroach demo`) are
  exempt — your 3-node cluster is not.
- Telemetry must reach Cockroach Labs on the free tier. A cluster on an air-gapped or
  firewalled machine will eventually be throttled even *with* a key.
- **READ COMMITTED, REPEATABLE READ, follower reads, and multi-region features are all
  licensed features.** Without a key, half this protocol silently does not work.
- Enterprise Free is free for students and academic researchers.

**Action:** obtain a free Enterprise license key from the Cockroach Labs Cloud Console
before day 1, then:

```sql
SET CLUSTER SETTING enterprise.license = '<your-key>';
SET CLUSTER SETTING cluster.organization = '<your university or name>';
```

**Failure signature if you skip this:** queries start returning notices about licensing,
then latency inflates cluster-wide, and your P-phase benchmark numbers become garbage
that looks like a CockroachDB performance problem. If throughput collapses inexplicably
mid-protocol, check the license before debugging anything else.

### 1.3 ⚠️ The v24.3.0 isolation-level trap

This is the single most important environment fact in this document.

In v24.3.0, weaker isolation levels are **gated behind cluster settings**, and when the
gate is closed CockroachDB **accepts your syntax and silently runs the transaction at a
stronger level.** `BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED` does not error — it
just gives you a SERIALIZABLE transaction.

- `sql.txn.read_committed_isolation.enabled` — gates READ COMMITTED.
- `sql.txn.repeatable_read_isolation.enabled` — gates REPEATABLE READ (which maps to
  SNAPSHOT isolation). **Introduced in v24.3.0 and disabled by default.**

If you do not check this, experiments I1–I5 will produce a table of results showing that
READ COMMITTED prevents write skew — a spectacular and entirely artefactual finding.

**Mandatory mitigation:** every isolation experiment must call `SHOW
transaction_isolation` *inside the open transaction* and record the answer. Never trust
the `BEGIN` statement. This is baked into the steps below; do not skip it.

### 1.4 Cluster startup

```bash
# Kill anything left over
pkill -f 'cockroach start' ; sleep 2
rm -rf ~/crdb ; mkdir -p ~/crdb

cockroach start --insecure \
  --store=$HOME/crdb/node1 --listen-addr=localhost:26257 --http-addr=localhost:8080 \
  --locality=region=eu-west-1,zone=a \
  --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background

cockroach start --insecure \
  --store=$HOME/crdb/node2 --listen-addr=localhost:26258 --http-addr=localhost:8081 \
  --locality=region=us-east-1,zone=b \
  --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background

cockroach start --insecure \
  --store=$HOME/crdb/node3 --listen-addr=localhost:26259 --http-addr=localhost:8082 \
  --locality=region=us-west-1,zone=c \
  --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background

cockroach init --insecure --host=localhost:26257
```

Node logs live at `~/crdb/nodeN/logs/cockroach.log`. Several experiments read them.

If `--background` is rejected or misbehaves on this build, fall back to:
`nohup cockroach start ... > ~/crdb/nodeN.out 2>&1 &`

**`--max-offset` constraints:** the value must be identical on every node. Changing it
requires stopping the **entire cluster** and restarting all nodes with the new value — a
rolling change is unsafe and CockroachDB may refuse it. K7 and K9 depend on this.

### 1.5 Sessions

Most experiments need 2–3 concurrent SQL sessions on *different gateway nodes*. Which
gateway a session uses matters — it determines the transaction's observed timestamps and
therefore the outcome of K8. Always label them:

```bash
# [A] gateway = n1
cockroach sql --insecure --host=localhost:26257 --database=seminar2
# [B] gateway = n2
cockroach sql --insecure --host=localhost:26258 --database=seminar2
# [M] monitor, gateway = n3
cockroach sql --insecure --host=localhost:26259 --database=seminar2
```

Use tmux or three terminal tabs. When you give the operator a step, prefix every block
with `[A]`, `[B]` or `[M]`.

**Anti-hang guard.** Several experiments deliberately create blocking. Have the operator
run this at the top of every session so a wedged experiment self-clears:

```sql
SET statement_timeout = '30s';
```

---

## 2. PHASE PRE — Preflight

Every one of these is a discovery step. Their output is not paper material; it is the
ground truth you will use to correct the rest of this document.

### PRE-1 — Version and cluster health

```sql
SELECT version();
SHOW CLUSTER SETTING version;
SELECT node_id, address, locality, is_live FROM crdb_internal.gossip_nodes ORDER BY node_id;
SELECT node_id, ranges, leases FROM crdb_internal.kv_store_status;
```

**Record:** exact build tag, all 3 nodes live, localities as configured.
**Abort if:** fewer than 3 live nodes, or the version is not v24.3.0. Everything
downstream assumes v24.3.0 semantics.

*(If `crdb_internal.kv_store_status` errors, drop it — it is a convenience check only.
`SHOW COLUMNS FROM crdb_internal.kv_store_status;` will tell you what is actually there.)*

### PRE-2 — License state

```sql
SELECT name, value FROM [SHOW CLUSTER SETTINGS] WHERE name IN ('enterprise.license','cluster.organization');
```

**Record:** whether a key is set. **Halt the whole protocol if not** — see §1.2.

### PRE-3 — Isolation gates (critical)

```sql
SELECT variable, value, description
FROM crdb_internal.cluster_settings
WHERE variable LIKE '%isolation%';
```

Then enable both weak levels:

```sql
SET CLUSTER SETTING sql.txn.read_committed_isolation.enabled = true;
SET CLUSTER SETTING sql.txn.repeatable_read_isolation.enabled = true;
```

Now **prove** they took effect — do not trust the `SET`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
COMMIT;

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SHOW transaction_isolation;
COMMIT;

BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
COMMIT;
```

**Expected:** `read committed`, `repeatable read` (or `snapshot`), `serializable`.
**If a level reports `serializable` when you asked for something weaker:** the gate is
still closed, or the feature needs a license. Fix it now. Do not proceed to phase I.

**Paper note for the operator:** the *default* value of these settings, and the fact that
CockroachDB silently upgrades rather than erroring, is itself a finding worth one
sentence in Chapter 3.3.

### PRE-4 — crdb_internal schema discovery

Run each and paste the column list. You will use these to correct queries later.

```sql
SHOW COLUMNS FROM crdb_internal.cluster_locks;
SHOW COLUMNS FROM crdb_internal.transaction_contention_events;
SHOW COLUMNS FROM crdb_internal.cluster_transactions;
SHOW COLUMNS FROM crdb_internal.cluster_sessions;
SHOW COLUMNS FROM crdb_internal.node_metrics;
SHOW COLUMNS FROM crdb_internal.cluster_contended_tables;
```

**Known protocol bug this catches:** `crdb_internal.cluster_transactions` has **no
`status` column**. If you have seen a plan that queries
`cluster_transactions WHERE status != 'IDLE'`, it is wrong — `status` lives on
`cluster_sessions`. Confirm this here and record the correction.

### PRE-5 — Metric name discovery

```sql
SELECT name, value FROM crdb_internal.node_metrics
WHERE name LIKE 'txn.%' ORDER BY name;

SELECT name, value FROM crdb_internal.node_metrics
WHERE name LIKE '%follower%' OR name LIKE '%closed_timestamp%' OR name LIKE '%clock-offset%'
ORDER BY name;
```

Metrics this protocol will want to use. **Confirm each exists before relying on it**; if
a name below is absent, find the nearest match in the output above and record the
substitution:

| Wanted | Used by | Meaning |
|---|---|---|
| `txn.commits1PC` | T3 | one-phase-commit fast path taken |
| `txn.parallelcommits` | T3 | parallel-commits protocol used |
| `txn.commits`, `txn.aborts` | T3, P2 | totals |
| `txn.restarts.serializable` | I3, P2 | serializable refresh failures |
| `txn.restarts.writetooold` | I4, P2 | write-too-old restarts |
| `txn.restarts.readwithinuncertainty` | K8 | uncertainty-interval restarts |
| `txn.restarts.txnpush` | C3 | push-induced restarts |
| `kv.follower_reads.success_count` | K5, K6 | reads served by a follower |
| `clock-offset.meannanos`, `clock-offset.stddevnanos` | K9 | measured inter-node clock offset |

**Important:** `node_metrics` is **per node**. A metric read on n1 does not include
counts from n2/n3. For any counter-delta measurement, query all three nodes and sum, or
use the aggregate:

```sql
SELECT name, sum(value) AS total
FROM crdb_internal.node_metrics
WHERE name IN ('txn.commits1PC','txn.parallelcommits')
GROUP BY name;
```

Verify whether `crdb_internal.node_metrics` on one gateway returns rows for all nodes or
only the local one — if only local, the operator must run the snapshot on each of the
three ports and you must sum the results. **Determine this in PRE-5 and record it.**

### PRE-6 — Baseline cluster settings snapshot

```sql
SELECT variable, value FROM crdb_internal.cluster_settings
WHERE variable LIKE '%closed_timestamp%'
   OR variable LIKE '%pipelin%'
   OR variable LIKE '%parallel_commit%'
   OR variable LIKE '%range_merge%'
   OR variable LIKE '%follower_read%'
   OR variable LIKE '%rangefeed%'
ORDER BY variable;
```

**Record all of it verbatim into `RESULTS.md` §Environment.** Every benchmark number in
the paper is meaningless without the settings it was produced under. Note in particular
the default of `kv.closed_timestamp.target_duration` — K5/K6 depend on it.

---

## 3. PHASE SETUP — Schema, seed, and range topology

### SETUP-1 — Schema

```sql
CREATE DATABASE IF NOT EXISTS seminar2;
USE seminar2;

-- Bank accounts. The money-conservation invariant on this table is the
-- correctness oracle for P2.
CREATE TABLE accounts (
    id          INT PRIMARY KEY,
    owner       STRING NOT NULL,
    balance     DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    region      STRING NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);
-- NOTE: deliberately NO `CHECK (balance >= 0)`.
-- A CHECK constraint would mask lost updates in P2 by rejecting the write that
-- destroys money. We want the anomaly to be *observable*, not prevented.
-- If you want a constraint demo, use a separate table.

-- Write-write conflict / deadlock target.
CREATE TABLE inventory (
    product_id  INT PRIMARY KEY,
    name        STRING NOT NULL,
    stock       INT NOT NULL DEFAULT 0,
    version     INT NOT NULL DEFAULT 1
);

-- Single hot key for contention experiments.
CREATE TABLE counters (
    id    INT PRIMARY KEY,
    name  STRING NOT NULL,
    value INT NOT NULL DEFAULT 0
);

-- Write-skew scenario (I3).
CREATE TABLE doctors (
    id      INT PRIMARY KEY,
    name    STRING NOT NULL,
    on_call BOOL NOT NULL DEFAULT true
);

-- Causal-order scenario (K3, K4).
-- NOTE: parent_id is deliberately NOT a foreign key. A self-referencing FK would
-- force the child insert to *read* the parent row, which makes the two transactions
-- conflict, which makes serializability forbid the reordering, which destroys the
-- experiment. This is the mechanism Cockroach Labs cite when they say the anomaly
-- "goes away" under an FK. Record that reasoning in the paper.
CREATE TABLE comments (
    id        INT PRIMARY KEY,
    parent_id INT NULL,
    body      STRING NOT NULL
);
```

### SETUP-2 — Seed

```sql
INSERT INTO accounts (id, owner, balance, region)
SELECT g, 'user_' || g::STRING, 10000.00,
       (ARRAY['eu-west-1','us-east-1','us-west-1'])[((g-1) % 3) + 1]
FROM generate_series(1, 10000) AS g;

INSERT INTO inventory (product_id, name, stock)
SELECT g, 'product_' || g::STRING, 100 FROM generate_series(1, 1000) AS g;

INSERT INTO counters (id, name, value) VALUES (1, 'global_counter', 0);
INSERT INTO doctors (id, name, on_call) VALUES (1, 'Alice', true), (2, 'Bob', true);
```

**Record the invariant baseline — P2 depends on this number:**

```sql
SELECT count(*) AS n_accounts, sum(balance) AS total_money FROM accounts;
-- expect: 10000, 100000000.00
```

### SETUP-3 — ⚠️ Range splits (this fixes the single biggest flaw in the naive plan)

**Why:** CockroachDB's default max range size is 512 MiB. Ten thousand narrow rows fit
in a **single range**. Without splitting, `id=1` and `id=5000` live on the same range,
served by the same leaseholder, and every "distributed transaction" experiment silently
degenerates into a single-range transaction. T3 in particular would measure the exact
opposite of its thesis.

```sql
-- Prevent the merge queue from undoing our work.
SET CLUSTER SETTING kv.range_merge.queue_enabled = false;

ALTER TABLE accounts SPLIT AT VALUES (2001), (4001), (6001), (8001);
ALTER TABLE accounts SCATTER;
```

**Verify — do not proceed until this passes:**

```sql
SHOW RANGES FROM TABLE accounts WITH DETAILS;
```

*(v23.1 changed `SHOW RANGES`. Leaseholder info requires `WITH DETAILS`. If the syntax
errors, run `SHOW RANGES FROM TABLE accounts;` and report the columns you get.)*

**Acceptance criteria:**

1. ≥ 5 ranges for `accounts`.
2. `id=1` and `id=9000` are in **different ranges** with **different leaseholders**.

Find the leaseholder for a specific key:

```sql
SELECT * FROM [SHOW RANGES FROM TABLE accounts WITH DETAILS]
WHERE start_key <= '/1' AND end_key > '/1';
```

**If leaseholders are co-located after SCATTER:** re-run `ALTER TABLE accounts SCATTER;`
(it is randomised). If it still won't separate them, use `ALTER RANGE ... RELOCATE LEASE
TO ...` — check the exact syntax on this build with `\h ALTER RANGE` first, and record
whatever syntax actually worked. **Do not proceed to T3 with co-located leaseholders.**

**Record for the paper:** a table of `range_id → start_key → end_key → leaseholder →
replicas`. This is Figure 1 material and it justifies every "distributed" claim you make
later.

Also split the comments table so K3/K4 can put parent and child on different ranges:

```sql
ALTER TABLE comments SPLIT AT VALUES (2);
ALTER TABLE comments SCATTER;
SHOW RANGES FROM TABLE comments WITH DETAILS;
```

### SETUP-4 — Reset helper

Several experiments mutate `accounts`. Give the operator this and have them run it
between experiments:

```sql
-- reset.sql
UPDATE accounts SET balance = 10000.00 WHERE balance != 10000.00;
UPDATE doctors SET on_call = true;
UPDATE counters SET value = 0 WHERE id = 1;
UPDATE inventory SET stock = 100, version = 1 WHERE stock != 100 OR version != 1;
DELETE FROM comments;
SELECT sum(balance) FROM accounts;  -- must print 100000000.00
```

---

## 4. THE PYTHON HARNESS

Everything that is *measured* goes through this, not through `cockroach sql -e`.

**Why this is non-negotiable:** a shell loop that calls `cockroach sql -e` once per
transaction spawns a process, builds a connection, and tears it down for every
iteration. Process startup dominates by an order of magnitude, so the loop measures your
laptop's fork/exec cost, not the database. Worse, `2>/dev/null` on such a loop hides
aborts — a run in which **every transaction fails** completes fastest and looks like a
win. Any benchmark built that way is unpublishable.

### 4.1 Install

```bash
python3 -m venv ~/crdb-venv
source ~/crdb-venv/bin/activate
pip install psycopg2-binary
```

### 4.2 `harness.py` — persistent connections, real timing, honest error accounting

```python
#!/usr/bin/env python3
"""Reusable measurement harness for the CockroachDB seminar experiments.

Design rules:
  - one long-lived connection per worker thread (no per-txn connect)
  - perf_counter around the transaction only
  - every outcome is counted: commit / retry / abort / error
  - emits CSV so results are reproducible and plottable
"""
import argparse, csv, json, random, statistics, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

import psycopg2
import psycopg2.errors

DSN = "postgresql://root@localhost:{port}/seminar2?sslmode=disable"
_local = threading.local()


def conn_for(port, isolation):
    """One connection per thread, isolation pinned at session level."""
    if not hasattr(_local, "conn"):
        c = psycopg2.connect(DSN.format(port=port))
        c.autocommit = False
        with c.cursor() as cur:
            cur.execute("SET default_transaction_isolation = %s", (isolation,))
            cur.execute("SET statement_timeout = '30s'")
            # PROOF, not trust: never rely on the SET having worked (see §1.3)
            cur.execute("SHOW transaction_isolation")
            actual = cur.fetchone()[0]
        c.commit()
        if actual.replace(" ", "_").lower() != isolation.replace(" ", "_").lower():
            raise SystemExit(
                f"FATAL: asked for {isolation!r}, session reports {actual!r}. "
                f"Check sql.txn.*_isolation.enabled cluster settings (see PRE-3)."
            )
        _local.conn = c
        _local.iso = actual
    return _local.conn


def run_txn(port, isolation, body, max_retries=10):
    """Execute `body(cur)` in a retry loop.

    Returns dict with outcome, attempts, latency_s, error.
    Latency covers ALL attempts, i.e. what the application actually waited.
    """
    c = conn_for(port, isolation)
    t0 = time.perf_counter()
    for attempt in range(1, max_retries + 1):
        try:
            with c.cursor() as cur:
                body(cur)
            c.commit()
            return {"outcome": "commit", "attempts": attempt,
                    "latency_s": time.perf_counter() - t0, "error": None}
        except psycopg2.errors.SerializationFailure as e:
            c.rollback()
            if attempt == max_retries:
                return {"outcome": "retry_exhausted", "attempts": attempt,
                        "latency_s": time.perf_counter() - t0, "error": str(e).strip()}
            # exponential backoff with jitter
            time.sleep(min(0.05 * (2 ** (attempt - 1)), 1.0) * random.uniform(0.5, 1.5))
        except Exception as e:
            c.rollback()
            return {"outcome": "error", "attempts": attempt,
                    "latency_s": time.perf_counter() - t0, "error": repr(e)}


def summarize(rows, label, extra=None):
    lat = sorted(r["latency_s"] for r in rows if r["outcome"] == "commit")
    def pct(p):
        return lat[min(int(len(lat) * p), len(lat) - 1)] * 1000 if lat else float("nan")
    out = {
        "label": label,
        "n": len(rows),
        "commits": sum(r["outcome"] == "commit" for r in rows),
        "retry_exhausted": sum(r["outcome"] == "retry_exhausted" for r in rows),
        "errors": sum(r["outcome"] == "error" for r in rows),
        "total_attempts": sum(r["attempts"] for r in rows),
        "retries": sum(r["attempts"] - 1 for r in rows),
        "p50_ms": round(pct(0.50), 2),
        "p95_ms": round(pct(0.95), 2),
        "p99_ms": round(pct(0.99), 2),
    }
    if extra:
        out.update(extra)
    return out


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)", file=sys.stderr)
```

### 4.3 Harness contract

When you (the supervisor) need a measurement, you write a small script that imports
`run_txn` / `summarize` and prints **JSON on stdout**. The operator pastes the JSON. You
never ask them to eyeball a latency off a terminal.

Every measurement script must print, at minimum:

```json
{"label":"...", "n":500, "commits":491, "retry_exhausted":0, "errors":9,
 "retries":133, "p50_ms":4.1, "p95_ms":22.7, "p99_ms":61.0,
 "isolation_verified":"serializable", "wall_s":31.2}
```

`isolation_verified` is mandatory and comes from `SHOW transaction_isolation`, not from
what was requested. If it is absent from the output, the run is `INCONCLUSIVE`.

---

## 5. PHASE T — Transaction Internals

### T1 — Write intents and the lock table

**Goal:** make the provisional-write mechanism visible.
**Hypothesis:** an uncommitted `UPDATE` leaves a row in `crdb_internal.cluster_locks`
identifying the holding transaction, the key, and the lock strength; it disappears on
commit.
**Refuted if:** no lock row appears, or it persists after `COMMIT`.

```sql
-- [A] gateway n1
BEGIN;
UPDATE accounts SET balance = balance - 500 WHERE id = 1;
-- do NOT commit
```

```sql
-- [M] gateway n3 — discovery first (R3)
SELECT DISTINCT lock_strength, durability FROM crdb_internal.cluster_locks;
```

**Do not assume `lock_strength = 'Exclusive'`.** In modern CockroachDB the lock strengths
are distinct values and a plain write intent is generally reported as `Intent`, whereas
`Exclusive` is what `SELECT ... FOR UPDATE` acquires. Read the actual output and use the
value you see. Getting this wrong is a common error in secondary sources.

```sql
-- [M] now the real query, using whatever columns PRE-4 said exist
SELECT range_id, table_name, lock_key_pretty, txn_id, ts,
       lock_strength, durability, granted, contended
FROM crdb_internal.cluster_locks
WHERE table_name = 'accounts';
```

```sql
-- [A]
COMMIT;
```

```sql
-- [M]
SELECT count(*) FROM crdb_internal.cluster_locks WHERE table_name = 'accounts';
```

**Capture:** the lock row before commit, the empty result after.
**Interpretation to write:** a write intent is one object doing two jobs — a provisional
MVCC value *and* a lock-table entry. That unification is why CockroachDB does not need a
separate lock manager replicated alongside the data, and it is what makes the intent
survive a coordinator crash (T4).

**Paper hook:** §3.1, Figure "write intent lifecycle".

---

### T2 — Tracing: what a transaction actually sends over the wire

**Goal:** observe transaction pipelining and the commit protocol directly, instead of
inferring them from latency.
**Depends on:** SETUP-3 (splits verified).

This replaces the common but broken approach of polling `crdb_internal` to "catch" the
`STAGING` transaction status. **You cannot observe `STAGING` from SQL** — the transaction
record lives in the KV layer and has no SQL surface. Polling for it will waste an hour
and produce nothing. Trace instead.

```sql
-- [A]
SET tracing = on;
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 9000;
COMMIT;
SET tracing = off;
SHOW TRACE FOR SESSION;
```

If the trace is too wide to read, query it:

```sql
SELECT span_idx, message_idx, operation, tag, message
FROM crdb_internal.session_trace
ORDER BY span_idx, message_idx;
```

**What to grep for, and what each means:**

| Look for | Meaning |
|---|---|
| `sending batch` / `sending partial batch` | one KV round trip; count them |
| `r<N>: sending batch` | which range each batch went to (should be ≥2 different ranges) |
| `Put`, `EndTxn` | the write and the commit request |
| `QueryIntent` | verification of a pipelined write — the parallel-commits signature |
| `async consensus` | a write that did not wait for Raft before returning — pipelining |
| `1PC` / `OnePhaseCommit` | the single-range fast path was taken |
| `pushing txn` / `resolving intent` | conflict machinery |

**R1 applies hard here.** Do not claim you saw a string you did not see. Paste the trace,
count the batches, and report exactly which of the above appear. If `async consensus`
does not appear, say so — that is a finding about this version and this workload, and it
is more interesting than a confirmation.

**Then run the contrast — a single-range transaction:**

```sql
SET tracing = on;
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- same range (verify!)
COMMIT;
SET tracing = off;
SHOW TRACE FOR SESSION;
```

**Deliverable:** a side-by-side table — *single-range txn* vs *multi-range txn* — of KV
round trips, ranges touched, and which protocol markers appear.

**Paper hook:** §3.2, Figure "trace of a distributed commit". A real trace excerpt is
worth more than a redrawn protocol diagram, because it is *your* evidence.

---

### T3 — One-phase commit vs. parallel commits (counter-based)

**Goal:** prove that a multi-range transaction uses the parallel-commits protocol and a
single-range transaction does not.
**Depends on:** SETUP-3, PRE-5.

**Why counters, not wall-clock.** All three nodes are on loopback. Inter-node RTT is
effectively zero, so the *latency* difference between a 1-round-trip commit and a
2-round-trip commit is buried in noise. The metric counters are exact, integral, and
immune to this. Measure what you can measure honestly.

**Method:**

1. Snapshot counters (on **all three** nodes if PRE-5 showed `node_metrics` is
   node-local — sum them):
   ```sql
   SELECT name, sum(value) AS v FROM crdb_internal.node_metrics
   WHERE name IN ('txn.commits','txn.commits1PC','txn.parallelcommits')
   GROUP BY name ORDER BY name;
   ```
2. Run **exactly 20** single-range transactions (ids 1 and 2 — confirm same range).
3. Snapshot again. Compute deltas.
4. Reset. Run **exactly 20** multi-range transactions (ids 1 and 9000 — confirm
   different ranges *and* different leaseholders).
5. Snapshot again. Compute deltas.

**Hypothesis:**
- Single-range arm: `Δtxn.commits1PC ≈ 20`, `Δtxn.parallelcommits ≈ 0`.
- Multi-range arm: `Δtxn.commits1PC ≈ 0`, `Δtxn.parallelcommits ≈ 20`.

**Important caveat you must handle:** the 1PC fast path generally requires the whole
transaction to arrive as **one batch**, i.e. an implicit/auto-committed statement. An
interactive `BEGIN; ...; ...; COMMIT;` sends each statement as a separate round trip and
may not qualify for 1PC even on a single range. So run **both forms** in the single-range
arm:

```sql
-- form (a): implicit, single statement, single range  -> best 1PC candidate
UPDATE accounts SET balance = balance + CASE id WHEN 1 THEN -100 ELSE 100 END
WHERE id IN (1, 2);

-- form (b): explicit multi-statement, single range
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```

This turns a possible embarrassment into a three-way result: **1PC is not "single-range",
it is "single-range AND single-batch"**. That distinction is a genuinely good paragraph
for §3.2 and most write-ups miss it.

**Report:** a 4-row table — {implicit single-range, explicit single-range, implicit
multi-range, explicit multi-range} × {Δcommits, Δcommits1PC, Δparallelcommits}.

**Optional latency arm (⚠️ requires root, run last):** inject one-way loopback latency so
round trips become visible. This delays only traffic *to* n2 and n3, leaving the client's
connection to n1 fast:

```bash
sudo tc qdisc add dev lo root handle 1: prio
sudo tc qdisc add dev lo parent 1:3 handle 30: netem delay 25ms
sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 \
     match ip dport 26258 0xffff flowid 1:3
sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 \
     match ip dport 26259 0xffff flowid 1:3

# ... re-run the T3 latency measurements via harness.py ...

# TEARDOWN — do not forget, it will poison every later experiment
sudo tc qdisc del dev lo root
```

Note it is a **one-way** delay: ~25 ms added per hop toward n2/n3, so expect ~25 ms of
added RTT, not 50 ms. Verify with `ping -c 3 localhost` before and after (ping is ICMP
and will *not* be affected by the port filter — instead verify by timing a
known-cross-node query). Record the teardown as a checklist item; a forgotten `netem`
rule silently inflates every subsequent number.

**Paper hook:** §3.2. This is your strongest empirical claim about parallel commits.

---

### T4 — Coordinator failure and recovery, timed

**Goal:** show atomicity survives the loss of the coordinating node, and **measure the
cost** of that survival.
⚠️ Kills a node.

**Hypothesis:** after `kill -9` of the gateway holding an in-flight transaction, the
intents are eventually cleaned up and the transaction is aborted; a reader that touches
those keys **blocks for several seconds** first, until the transaction record's heartbeat
is judged expired.

**The interesting number is that delay** — it is the price CockroachDB pays to avoid the
blocking-forever failure mode of classic 2PC, and nobody measures it.

```sql
-- [A] gateway n1
BEGIN;
UPDATE accounts SET balance = balance - 1000 WHERE id = 1;
UPDATE accounts SET balance = balance + 1000 WHERE id = 9000;
-- intents now placed on two ranges; do NOT commit
```

```bash
# [terminal 3] ⚠️ hard-kill the coordinator
pkill -9 -f 'crdb/node1'
```

Now, from **[B] on n2**, time the read. Use a script, not a stopwatch:

```python
import psycopg2, time
c = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable")
c.autocommit = True
t0 = time.perf_counter()
with c.cursor() as cur:
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    v = cur.fetchone()[0]
print({"blocked_s": round(time.perf_counter()-t0, 3), "balance": str(v)})
```

**Expected:** `balance = 10000.00` (rolled back), `blocked_s` in the low single-digit
seconds. Repeat 5× (restart node1 and redo the setup each time) and report
min/median/max per R4.

**Also capture:**

```sql
-- [B] liveness
SELECT node_id, is_live FROM crdb_internal.gossip_nodes ORDER BY node_id;
```

```bash
# grep the surviving nodes' logs for the recovery path
grep -iE 'intent|abort|txn.*expire|heartbeat' ~/crdb/node2/logs/cockroach.log | tail -40
```

**Restart and verify:**

```bash
cockroach start --insecure \
  --store=$HOME/crdb/node1 --listen-addr=localhost:26257 --http-addr=localhost:8080 \
  --locality=region=eu-west-1,zone=a --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background
```

```sql
SELECT sum(balance) FROM accounts;  -- must still be 100000000.00
```

**Interpretation to write:** name the actual mechanism. The transaction record is a
Raft-replicated KV row, so it outlives its coordinator; a reader that finds an orphaned
intent looks up that record, finds it `PENDING` with a stale heartbeat, and pushes it to
`ABORTED`. Classic 2PC blocks indefinitely here because the prepare-state lives *only* on
the coordinator. Contrast this with Gray & Lamport's Paxos Commit, which is the same idea
— replicate the coordinator's decision — reached from the other direction.

**Paper hook:** §3.2 / §2.2 contrast, and the `blocked_s` distribution is a figure.

---

## 6. PHASE I — Isolation Levels

**Global precondition for every experiment in this phase:** PRE-3 passed, and each
transaction prints `SHOW transaction_isolation` inside itself. An isolation result
without that proof is `INCONCLUSIVE` (§1.3).

Run each anomaly at **all three levels**: `SERIALIZABLE`, `REPEATABLE READ` (= SNAPSHOT),
`READ COMMITTED`. The three-column result table is the deliverable for Chapter 3.3.

### I1 — Non-repeatable read

**Hypothesis:** allowed at READ COMMITTED; prevented at REPEATABLE READ and SERIALIZABLE.

```sql
-- [A]
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;           -- PROOF
SELECT balance FROM accounts WHERE id = 1;
```
```sql
-- [B]
UPDATE accounts SET balance = 5000 WHERE id = 1;   -- implicit txn, commits now
```
```sql
-- [A]
SELECT balance FROM accounts WHERE id = 1;         -- changed? -> anomaly
COMMIT;
```

Repeat verbatim with `REPEATABLE READ`, then `SERIALIZABLE`. Reset between runs.

**Mechanism to explain (this is the part most write-ups skip):** at SERIALIZABLE and
REPEATABLE READ, A's reads are pinned to a single MVCC snapshot, so B's later write is
simply invisible to A. B is *not blocked* by A's read — A's read left an entry in the
**timestamp cache**, which forces B's write to take a timestamp above A's read timestamp.
Naming the timestamp cache here is what turns a screenshot into an explanation.

### I2 — Phantom read

Same shape, but with a predicate:

```sql
-- [A]
BEGIN TRANSACTION ISOLATION LEVEL <X>;
SHOW transaction_isolation;
SELECT count(*) FROM accounts WHERE balance > 9999;
```
```sql
-- [B]
INSERT INTO accounts (id, owner, balance, region) VALUES (99999, 'phantom', 99999, 'eu-west-1');
```
```sql
-- [A]
SELECT count(*) FROM accounts WHERE balance > 9999;   -- count changed? -> phantom
COMMIT;
```
Cleanup: `DELETE FROM accounts WHERE id = 99999;`

**Note the theoretical subtlety for the paper:** ANSI REPEATABLE READ permits phantoms
but *prevents* write skew; snapshot isolation is the mirror image — it prevents phantoms
but permits write skew. CockroachDB's `REPEATABLE READ` is snapshot isolation, so what
you observe here may not match the ANSI name. Whatever you observe, report it, and use
the discrepancy: it is a concrete illustration of why Berenson et al. argued the ANSI
definitions are broken, and why Adya's phenomena-based definitions replaced them.

### I3 — Write skew (the on-call doctors)

**Hypothesis:** allowed at READ COMMITTED and REPEATABLE READ/SNAPSHOT; prevented at
SERIALIZABLE via a failed read refresh, surfacing as SQLSTATE 40001.

```sql
-- reset
UPDATE doctors SET on_call = true;
```
```sql
-- [A]
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
SELECT count(*) FROM doctors WHERE on_call = true;   -- 2 -> "safe to go off call"
UPDATE doctors SET on_call = false WHERE id = 1;
-- hold
```
```sql
-- [B]
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SHOW transaction_isolation;
SELECT count(*) FROM doctors WHERE on_call = true;
UPDATE doctors SET on_call = false WHERE id = 2;
COMMIT;
```
```sql
-- [A]
COMMIT;   -- expect SQLSTATE 40001
SELECT count(*) FROM doctors WHERE on_call = true;   -- expect 1
```

**Capture the FULL error string, not a paraphrase.** CockroachDB's retry errors carry a
*reason code* (e.g. `RETRY_SERIALIZABLE`, `RETRY_WRITE_TOO_OLD`) and the reason is the
interesting part — it tells you *which* mechanism fired. Paste it verbatim.

Then repeat at `READ COMMITTED` and `REPEATABLE READ`. Expect both commits to succeed and
`count(*) = 0` — nobody on call.

**Two honest caveats to record:**
1. **Which** transaction receives the 40001 is not deterministic. Note that; don't
   present it as if A always loses.
2. B's `SELECT count(*)` scans rows including the one A has an intent on, so B may
   **block** until A releases. If the sessions interleave differently than scripted, the
   error may land on B. Report what happened.

### I4 — Lost update (the one the naive plan gets wrong)

**Why this experiment exists.** A single-statement `UPDATE counters SET value = value + 1`
re-reads the row under lock, so it yields the correct count at *every* isolation level. It
does not discriminate and it is not a lost-update demo. A real lost update needs a
**read, then a decision, then a write, across two statements**.

**Hypothesis:** READ COMMITTED permits the lost update; SERIALIZABLE rejects it with
SQLSTATE 40001 (expect reason `RETRY_WRITE_TOO_OLD`).

```sql
UPDATE counters SET value = 0 WHERE id = 1;
```
```sql
-- [A]
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
SELECT value FROM counters WHERE id = 1;    -- reads 0
```
```sql
-- [B]
UPDATE counters SET value = 5 WHERE id = 1; -- commits: value = 5
```
```sql
-- [A] -- application logic: "I read 0, so I write 0 + 1"
UPDATE counters SET value = 1 WHERE id = 1;
COMMIT;
SELECT value FROM counters WHERE id = 1;    -- 1 -> B's update was LOST
```

Repeat at `SERIALIZABLE`: A's commit should fail with 40001.
Repeat at `REPEATABLE READ` and record which way snapshot isolation falls.

**Paper hook:** §3.3. Pair this table with I3 — write skew and lost update are the two
anomalies that separate the levels that matter in practice, and both are *invisible* in
the classic dirty-read/phantom-read anomaly table. That is exactly Cockroach Labs'
argument for why the anomaly table is the wrong teaching tool.

### I5 — `SELECT ... FOR UPDATE` as the READ COMMITTED mitigation

**Goal:** show that RC can be made safe by explicit locking, and that this is not free.

Re-run I4 at READ COMMITTED with the read replaced by:

```sql
SELECT value FROM counters WHERE id = 1 FOR UPDATE;
```

**Expected:** B now blocks until A commits; no lost update.

Also try `FOR SHARE` and record whether it prevents the anomaly (it should not — a shared
lock does not exclude the concurrent writer's exclusive acquisition, but *verify*, do not
assert).

Check what lock this actually took:

```sql
-- [M] while A holds it
SELECT lock_key_pretty, lock_strength, durability, granted
FROM crdb_internal.cluster_locks WHERE table_name = 'counters';
```

**Compare `lock_strength` and `durability` here against T1's plain-intent output.** That
contrast — unreplicated `Exclusive` lock vs replicated `Intent` — is a concrete detail
almost nothing outside the source code will tell you, and you measured it.

**Interpretation for the paper:** this is the ACIDRain critique in miniature. Weak
isolation plus manual `FOR UPDATE` is *sound in principle and unreliable in practice*,
because correctness now depends on the developer identifying every read that feeds a
write. P2 quantifies what you pay for it.

### I6 — Isolation and staleness interact: RC + `AS OF SYSTEM TIME`

**Goal:** a small, sharp demonstration that isolation level and read timestamp are not
independent knobs.

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED AS OF SYSTEM TIME '-10s';
SHOW transaction_isolation;
SELECT balance FROM accounts WHERE id = 1;
COMMIT;
```

**Hypothesis:** the transaction is *promoted* to a read-only SERIALIZABLE transaction,
because READ COMMITTED takes a fresh snapshot per statement, which is incoherent with
pinning the whole transaction to a historical timestamp. PostgreSQL rejects the analogous
combination outright; CockroachDB accepts the syntax and upgrades instead.

**Report whatever `SHOW transaction_isolation` actually says.** Either answer is a good
two-sentence finding for §3.3/§3.5.

---

## 7. PHASE C — Conflict Detection and Resolution

### C1 — Write-write conflict and the lock wait queue

```sql
-- [A]
BEGIN;
UPDATE inventory SET stock = stock - 1, version = version + 1 WHERE product_id = 1;
```
```sql
-- [B]
BEGIN;
UPDATE inventory SET stock = stock - 1, version = version + 1 WHERE product_id = 1;
-- blocks
```
```sql
-- [M]
SELECT lock_key_pretty, txn_id, lock_strength, granted, contended
FROM crdb_internal.cluster_locks WHERE table_name = 'inventory';
-- expect: one row granted=true (A), one row granted=false (B) queued
```
```sql
-- [A]
COMMIT;   -- B unblocks
```
```sql
-- [B]
COMMIT;
```
```sql
-- [M] contention events are recorded asynchronously; wait a few seconds
SELECT collection_ts, contention_duration, waiting_txn_id, blocking_txn_id,
       waiting_txn_fingerprint_id, blocking_txn_fingerprint_id
FROM crdb_internal.transaction_contention_events
ORDER BY collection_ts DESC LIMIT 5;
```

**Time B's block** with the harness so you have a number, not an impression.
**Capture:** the `granted=false` row — that is the wait queue, visible.

### C2 — Deadlock detection

```sql
-- [A]
BEGIN; UPDATE accounts SET balance = balance - 10 WHERE id = 1;
-- [B]
BEGIN; UPDATE accounts SET balance = balance - 10 WHERE id = 9000;
-- [A]
UPDATE accounts SET balance = balance + 10 WHERE id = 9000;   -- waits on B
-- [B]
UPDATE accounts SET balance = balance + 10 WHERE id = 1;      -- waits on A -> cycle
```

**Hypothesis:** one transaction is aborted; the error names deadlock or a push.
**Capture:** the exact error text and **which** transaction lost. Repeat 5×; report the
distribution of who loses. If it is not 50/50, say so and reason about why (transaction
age and priority both feed the push decision).

Note `id=1` and `id=9000` are on **different ranges with different leaseholders** after
SETUP-3, so this is a genuinely *distributed* deadlock — the cycle spans nodes. Say that
in the paper; it is the whole point, and a same-range deadlock would not demonstrate it.

### C3 — Transaction priority and the push mechanism

```sql
-- [A] low-priority writer
BEGIN PRIORITY LOW;
UPDATE accounts SET balance = balance - 1 WHERE id = 1;
```
```sql
-- [M] high-priority reader
BEGIN PRIORITY HIGH;
SELECT balance FROM accounts WHERE id = 1;
COMMIT;
```
```sql
-- [A]
COMMIT;   -- expect: aborted
```

**Hypothesis:** the HIGH reader pushes A to `ABORTED` rather than waiting; A's commit
fails.
**Then invert it:** make the reader `PRIORITY LOW` against a `PRIORITY HIGH` writer and
show the reader waits instead.

**Capture:** `txn.restarts.txnpush` / `txn.restarts.txnaborted` deltas from
`node_metrics`, and the error text.

**Interpretation:** this is the resolution rule behind everything in phase C — a
conflicting operation does not simply queue, it *attempts a push*, and priority plus
transaction age decide whether the push aborts the other transaction or the pusher waits.

---

## 8. PHASE K — Consistency

This is the phase that earns the word "Consistency" in the title, and it is the phase
most CockroachDB write-ups skip. The framing for the whole chapter:

> **Isolation and consistency are orthogonal axes.** Isolation constrains how concurrent
> *transactions* interleave (serializability). Consistency constrains what a *read* may
> return given real time and replication (linearizability). Combining both gives strict
> serializability. CockroachDB sits at **more than serializable, less than strictly
> serializable**: it guarantees no stale reads, but permits one anomaly — *causal
> reverse* — because it uses hybrid logical clocks and an assumed maximum clock offset
> rather than Google's TrueTime.

Every experiment below is evidence for one part of that sentence.

### K1 — The positive guarantee: no stale reads across gateways

**Goal:** establish the guarantee CockroachDB *does* make, before probing the one it
doesn't.
**Hypothesis:** a read transaction that *starts after* a write transaction committed will
always observe that write, regardless of which node serves the read.

```python
#!/usr/bin/env python3
"""K1: no-stale-reads probe. Write on n1, immediately read on n2 and n3."""
import psycopg2, time, json

w = psycopg2.connect("postgresql://root@localhost:26257/seminar2?sslmode=disable"); w.autocommit = True
r2 = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable"); r2.autocommit = True
r3 = psycopg2.connect("postgresql://root@localhost:26259/seminar2?sslmode=disable"); r3.autocommit = True

N, stale = 1000, 0
for i in range(N):
    with w.cursor() as cur:                       # write completes (committed) here
        cur.execute("UPDATE counters SET value = %s WHERE id = 1", (i,))
    for c, tag in ((r2, "n2"), (r3, "n3")):       # reads START after the commit returned
        with c.cursor() as cur:
            cur.execute("SELECT value FROM counters WHERE id = 1")
            v = cur.fetchone()[0]
        if v != i:
            stale += 1
            print(f"STALE on {tag}: wrote {i}, read {v}")
print(json.dumps({"iterations": N, "reads": 2*N, "stale_reads": stale}))
```

**Expected:** `stale_reads: 0`. A non-zero count would be a serious CockroachDB bug and
you should double-check the script before believing it.

**Interpretation:** this is the C in CAP, and it is the property that makes the "just use
follower reads" advice a real trade rather than a free lunch. Note *why* it holds: every
default read is routed to the range's **leaseholder**, and the leaseholder is the single
serialization point for that range. Also record the honest limitation: on one machine
your writer and reader share a clock, so this test cannot distinguish "CockroachDB
guarantees it" from "there was no skew to expose". You are confirming the mechanism, not
stress-testing it.

**Paper hook:** §3.5, and the counter-example for §2.4's eventual-consistency section.

### K2 — Reads block on writes — and it is consistency, not isolation

**This is the highest-value experiment in the phase.** It empirically falsifies the single
most common misconception about CockroachDB, and Cockroach Labs have written that the
misconception is exactly this: people attribute read-blocking to SERIALIZABLE and propose
a weaker isolation level as the fix, when the blocking actually comes from the
consistency model.

**Hypothesis:** a reader that encounters an uncommitted write intent blocks for
essentially the same duration at **all three** isolation levels. Isolation level does not
change it.
**Refuted if:** READ COMMITTED does not block, or blocks measurably less.

```python
#!/usr/bin/env python3
"""K2: does the reader's isolation level change how long it blocks on an intent?"""
import psycopg2, threading, time, json, statistics

WRITER = "postgresql://root@localhost:26257/seminar2?sslmode=disable"   # n1
READER = "postgresql://root@localhost:26258/seminar2?sslmode=disable"   # n2
HOLD_S = 3.0
LEVELS = ["serializable", "repeatable read", "read committed"]

def trial(level):
    w = psycopg2.connect(WRITER); w.autocommit = False
    r = psycopg2.connect(READER); r.autocommit = False
    try:
        with w.cursor() as cur:                       # place an intent, hold it
            cur.execute("UPDATE accounts SET balance = balance - 1 WHERE id = 1")
        with r.cursor() as cur:
            cur.execute("SET default_transaction_isolation = %s", (level,))
        r.commit()
        with r.cursor() as cur:
            cur.execute("SHOW transaction_isolation")
            verified = cur.fetchone()[0]              # PROOF (see §1.3)

        result = {}
        def reader():
            t0 = time.perf_counter()
            with r.cursor() as cur:
                cur.execute("SELECT balance FROM accounts WHERE id = 1")
                result["value"] = str(cur.fetchone()[0])
            result["blocked_s"] = round(time.perf_counter() - t0, 3)
        th = threading.Thread(target=reader); th.start()
        time.sleep(HOLD_S)
        w.commit()                                     # release the intent
        th.join(timeout=30)
        r.commit()
        return {"requested": level, "verified": verified, **result}
    finally:
        w.close(); r.close()

out = []
for lvl in LEVELS:
    runs = [trial(lvl) for _ in range(5)]             # R4: N>=5
    b = sorted(x["blocked_s"] for x in runs)
    out.append({"level": lvl, "verified": runs[0]["verified"],
                "hold_s": HOLD_S, "blocked_min": b[0],
                "blocked_median": b[len(b)//2], "blocked_max": b[-1],
                "value_seen": runs[0]["value"]})
print(json.dumps(out, indent=2))
```

**Expected shape:** `blocked_median ≈ 3.0` for all three levels — the reader waits for the
writer, whatever isolation it asked for.

**Why it happens (this is the paragraph the paper needs):** the reader cannot ignore the
intent. If it skipped it, and the writer then committed at a timestamp *below* the
reader's read timestamp, the reader would have returned a stale value — violating the K1
guarantee. So the reader must resolve the intent. It attempts to push the writer, the
push against a live, heartbeating transaction does not succeed, and the reader queues in
the lock table. **Nothing in that chain mentions isolation.** Weakening isolation cannot
fix it, because it is the price of "no stale reads."

**Paper hook:** §2.1 (the isolation-vs-consistency distinction), §3.4, and it is your
strongest slide. Put the three-row table on it.

### K3 — MVCC timestamp order ≠ real-time order

**Goal:** demonstrate the mechanism underlying causal reverse — that two independent
transactions can be assigned MVCC timestamps in the opposite order to the one in which
they started.
**Depends on:** SETUP-1 (`comments` has *no* FK — see the note in the schema).

Recipe. Run each block in the labelled session, in this exact order:

```sql
-- [A] gateway n1 — will insert the PARENT
BEGIN;
SHOW transaction_isolation;                       -- serializable
SELECT * FROM comments WHERE id = 1;              -- empty; fixes A's read timestamp
```
```sql
-- [B] gateway n2 — inserts the CHILD, commits immediately, at a timestamp ABOVE A's
INSERT INTO comments (id, parent_id, body) VALUES (2, 1, 'OP is wrong');
```
```sql
-- [M] gateway n3 — read key 1. This leaves a timestamp-cache entry for that key
--     at a timestamp above B's commit. This is the lever.
SELECT * FROM comments WHERE id = 1;              -- still empty
```
```sql
-- [A] — this write must now take a timestamp ABOVE M's read, i.e. above B's commit
INSERT INTO comments (id, parent_id, body) VALUES (1, NULL, 'a root comment');
COMMIT;
```
```sql
-- [M] the payoff
SELECT id, parent_id, crdb_internal_mvcc_timestamp
FROM comments ORDER BY id;
```

**Expected:** row `1` (the parent, inserted first) carries a **higher**
`crdb_internal_mvcc_timestamp` than row `2` (the child, inserted second).

**Mechanism:** A's `INSERT` collides with the timestamp-cache entry left by M's read, so
A's write timestamp is forwarded above it. Under SERIALIZABLE, A must commit at its read
timestamp, so it performs a **read refresh** — it re-checks that nothing it read changed
in the interval. Nothing wrote key 1, so the refresh succeeds and A commits at the
forwarded timestamp with no error.

**Failure modes and what to do:**
- A's `COMMIT` returns 40001 `RETRY_SERIALIZABLE` → the refresh failed. Reset, retry the
  recipe. If it fails repeatedly, record that and note it as an observed property of the
  refresh path.
- Timestamps come out in the "expected" order (parent lower) → the push did not happen.
  Check that M's read really did precede A's insert. Report the negative result.

**Honest framing — do not overclaim (R6, §12):** this shows MVCC order diverging from
start order for two *overlapping* transactions. That is **legitimate** under
serializability and is **not** a strict-serializability violation, because A and B were
concurrent. It is the *mechanism* that causal reverse rides on, not causal reverse itself.
Say exactly that.

### K4 — A historical read that sees the child without the parent

**Depends on:** K3 (run it immediately after, without resetting).

You now have `comments` where the child's MVCC timestamp is below the parent's. Pick a
timestamp strictly between them:

```sql
-- [M] read the two timestamps
SELECT id, crdb_internal_mvcc_timestamp FROM comments ORDER BY id;
```

Take a value between them and:

```sql
SELECT * FROM comments AS OF SYSTEM TIME '<T_between>' ORDER BY id;
```

**Expected:** row `2` (the reply) is returned; row `1` (the thing it replies to) is not.
**A historical read returns a reply to a comment that does not exist.**

**Why this matters beyond a party trick:** `BACKUP` uses `AS OF SYSTEM TIME` internally.
A backup taken at an unlucky timestamp can contain the child and not the parent. That is a
real operational consequence of a real consistency property, and it is a much better
conclusion for §3.5 than "follower reads are stale."

**Then demonstrate the fix**, which is also the theory:

```sql
CREATE TABLE comments_fk (
    id        INT PRIMARY KEY,
    parent_id INT NULL REFERENCES comments_fk(id),
    body      STRING NOT NULL
);
```

Re-run the K3 recipe against `comments_fk`. Now the child insert must *read* the parent
row to check the FK, so the two transactions' read/write sets overlap, so serializability
forbids the reordering outright. **Report whether the anomaly disappears.** If it does,
you have empirically demonstrated the exact escape hatch Cockroach Labs point to: the
anomaly requires the two transactions to be genuinely independent, and a foreign key
makes them dependent.

**Paper hook:** §3.5, and this pair (K3+K4) is the intellectual core of the consistency
chapter.

### K5 — Follower reads: finding the staleness threshold

**Goal:** measure how stale a read must be before a follower will serve it, and tie that
number to the closed timestamp.

**Why not measure latency.** On loopback, a follower read is not faster than a leaseholder
read — there is no WAN round trip to save. Latency here measures nothing. **Measure the
counter instead**: `kv.follower_reads.success_count` tells you, exactly and integrally,
whether the read was served by a follower. This is the right observable and it works fine
on a laptop.

**Method (sweep):**

1. Read `kv.closed_timestamp.target_duration` and
   `kv.closed_timestamp.side_transport_interval` from PRE-6. Record the defaults.
2. Pick a key whose leaseholder is **not** n2 (from SETUP-3's range table). Connect to
   **n2**, which therefore holds a follower replica.
3. For each staleness `S` in `{0 (strong), 100ms, 500ms, 1s, 2s, 3s, 4s, 5s, 10s}`:
   - snapshot `kv.follower_reads.success_count` (all nodes, summed)
   - issue 50 reads: `SELECT ... AS OF SYSTEM TIME '-<S>' WHERE id = <key>`
   - snapshot again; record the delta
4. Also test the two supported forms:
   ```sql
   SELECT balance FROM accounts AS OF SYSTEM TIME follower_read_timestamp() WHERE id = 9000;
   SELECT balance FROM accounts AS OF SYSTEM TIME with_max_staleness('10s') WHERE id = 9000;
   SELECT balance FROM accounts AS OF SYSTEM TIME with_max_staleness('10s', true) WHERE id = 9000;
   ```
5. Confirm the plan agrees:
   ```sql
   EXPLAIN (VERBOSE) SELECT balance FROM accounts
   AS OF SYSTEM TIME follower_read_timestamp() WHERE id = 9000;
   ```

**Report:** a table of `staleness → Δfollower_reads.success_count`, and the **minimum
staleness at which the delta becomes non-zero**. That threshold is your measurement.

**Predictions to check, not assume:**
- Strong reads (S=0) never increment the counter.
- The threshold sits near `kv.closed_timestamp.target_duration` plus propagation, and
  `follower_read_timestamp()` is a helper that returns a timestamp guaranteed to be past
  it — this is precisely why hard-coding `AS OF SYSTEM TIME '-10s'` is a worse habit than
  calling the function.

**Also record the bounded-staleness restrictions** by provoking them — they are real
limitations worth a paragraph:
```sql
-- expect an error: bounded staleness has restrictions (single statement, no joins, etc.)
SELECT a.balance, b.balance FROM accounts a JOIN accounts b ON a.id = b.id - 1
AS OF SYSTEM TIME with_max_staleness('10s') LIMIT 1;
```
Report the actual error text.

### K6 — Moving the threshold: closed-timestamp tuning

**Depends on:** K5. ⚠️ Changes a cluster-wide setting.

```sql
SET CLUSTER SETTING kv.closed_timestamp.target_duration = '500ms';
```

Wait ~30s for it to propagate, then **re-run the K5 sweep verbatim**.

**Hypothesis:** the minimum staleness at which follower reads succeed drops roughly in
proportion.

**Restore afterwards** (record the original from PRE-6):
```sql
SET CLUSTER SETTING kv.closed_timestamp.target_duration = '3s';
```

**Interpretation:** this is the consistency/staleness dial made concrete. The closed
timestamp is a promise that no future write will land below it, which is exactly what
lets a follower serve a read without asking the leaseholder. Tightening it buys fresher
follower reads and costs more side-transport traffic. Present K5+K6 as one figure: two
threshold curves.

### K7 — GLOBAL tables: paying for consistency in milliseconds, on a laptop

**This is the experiment that makes the clock-offset assumption tangible**, and it works
on loopback precisely *because* the cost is not network latency — it is a deliberate
wait.

⚠️ Requires a full cluster restart for the second arm. Do K7 and K9 in one sitting.
⚠️ Uses a **separate database** so it does not disturb `seminar2`'s range layout.

**Setup (arm 1, `--max-offset=500ms`):**

```sql
CREATE DATABASE mrtest;
ALTER DATABASE mrtest SET PRIMARY REGION 'eu-west-1';
ALTER DATABASE mrtest ADD REGION 'us-east-1';
ALTER DATABASE mrtest ADD REGION 'us-west-1';
SHOW REGIONS FROM DATABASE mrtest;
USE mrtest;

CREATE TABLE t_global   (id INT PRIMARY KEY, v STRING) LOCALITY GLOBAL;
CREATE TABLE t_regional (id INT PRIMARY KEY, v STRING) LOCALITY REGIONAL BY TABLE IN PRIMARY REGION;
INSERT INTO t_global   SELECT g, 'x' FROM generate_series(1,100) g;
INSERT INTO t_regional SELECT g, 'x' FROM generate_series(1,100) g;

SELECT variable, value FROM crdb_internal.cluster_settings
WHERE variable LIKE '%lead_for_global%' OR variable LIKE '%closed_timestamp%';
```

**Measure** with the harness — 100 single-row updates to each table, median/p95:

```python
# 100x:  UPDATE t_global   SET v = 'y' WHERE id = <random 1..100>
# 100x:  UPDATE t_regional SET v = 'y' WHERE id = <random 1..100>
# also measure reads of each from n2 and n3
```

**Hypothesis (arm 1):** writes to `t_global` are **hundreds of milliseconds slower** than
writes to `t_regional`, despite zero network latency between the nodes. Reads of
`t_global` from any node are fast and non-blocking.

**Arm 2 — halve the clock-offset assumption.** ⚠️ Stop **all three** nodes, restart all
three with `--max-offset=250ms` (the value must be identical on every node; a rolling
change is unsafe and may be refused), then re-measure.

```bash
pkill -f 'cockroach start'; sleep 5
# restart all three nodes exactly as in §1.4 but with --max-offset=250ms
```

**Hypothesis (arm 2):** the `t_global` write penalty shrinks roughly in proportion to
`max-offset`; `t_regional` is unaffected.

**Report:** a 2×2 table — {global, regional} × {max-offset 500ms, 250ms} — of median and
p95 write latency, plus read latency from each node.

**Interpretation — this is the whole thesis of the paper in one number.** A GLOBAL table
range is *non-blocking*: it commits writes at a timestamp in the **future** and waits out
the interval, so that every replica can serve a strongly-consistent read locally without
contacting the leaseholder. The size of that future interval is a function of the maximum
clock offset the cluster assumes. You have therefore measured, directly, the price of
CockroachDB's decision to assume bounded clock skew instead of measuring it with
TrueTime — and shown that tightening the assumption makes writes cheaper. Cockroach Labs
document exactly this recommendation (lower `--max-offset` to 250ms for multi-region
clusters using global tables, to reduce global-table write latency); your two arms
**quantify** their advice.

Restore `--max-offset=500ms` before continuing, or record that the remaining experiments
ran at 250ms.

### K8 — Uncertainty intervals

**Goal:** trigger and count `ReadWithinUncertaintyIntervalError` — the mechanism that
buys the K1 guarantee without atomic clocks.
**Depends on:** SETUP-3 (multiple ranges with leaseholders on different nodes).

**Why this fires even with perfectly synchronised clocks.** The uncertainty interval is
not about *actual* skew; it is about *possible* skew. A transaction with timestamp `T` has
an uncertainty window `[T, T + max_offset]`. Any value it encounters with an MVCC
timestamp in that window *might* have been committed before the transaction began, by a
node whose clock runs ahead — so the transaction cannot safely ignore it and must restart
at a higher timestamp. CockroachDB narrows this window using **observed timestamps**: once
a transaction has talked to a node, it knows that node's clock reading and can rule out
"future" values from it. **So the trick is to read from a node the transaction has not
contacted yet.**

```python
#!/usr/bin/env python3
"""K8: provoke ReadWithinUncertaintyIntervalError on a zero-skew cluster.

Recipe:
  A (gateway n1) begins, reads key K1 -> fixes A's timestamp, records an observed
    timestamp for n1 only.
  B (gateway n2) writes key K2 -> commits at a timestamp just above A's.
  A reads K2, whose leaseholder A has never contacted -> the value falls in A's
    uncertainty window -> restart error.
All three steps must fit inside max_offset (500ms). A script does; a human does not.

K1 and K2 MUST be on different ranges with different leaseholders (see SETUP-3),
and A's first read must have returned rows to the client, so CockroachDB cannot
transparently retry the transaction server-side and must surface the error.
"""
import psycopg2, psycopg2.errors, json, sys

K1, K2 = 1, 9000          # verify with SHOW RANGES that these differ (SETUP-3)
ATTEMPTS = 100

hits, other, ok = 0, [], 0
for i in range(ATTEMPTS):
    # NOTE: psycopg2 issues BEGIN implicitly on the first statement of a non-autocommit
    # connection. Do NOT also execute BEGIN/COMMIT by hand here -- that raises
    # "there is already a transaction in progress" and every attempt lands in
    # other_errors, which looks exactly like "the experiment didn't fire".
    a = psycopg2.connect("postgresql://root@localhost:26257/seminar2?sslmode=disable")
    b = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable")
    b.autocommit = True
    try:
        # Optional: flush results to the client so CockroachDB cannot transparently
        # retry the txn server-side and hide the error. Set it outside a txn.
        # Verify it exists on this build (SHOW ALL); drop this block if not.
        a.autocommit = True
        try:
            with a.cursor() as cur:
                cur.execute("SET results_buffer_size = 0")
        except Exception:
            pass
        a.autocommit = False

        with a.cursor() as cur:                  # implicit BEGIN: A's timestamp is fixed here
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K1,))
            cur.fetchall()                       # results returned -> no silent server-side retry
        with b.cursor() as cur:                  # B writes K2 at a slightly higher ts
            cur.execute("UPDATE accounts SET balance = balance + 0.01 WHERE id = %s", (K2,))
        with a.cursor() as cur:                  # K2's leaseholder is a node A has not contacted
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K2,))
            cur.fetchall()
        a.commit()
        ok += 1
    except psycopg2.errors.SerializationFailure as e:
        msg = str(e)
        if "uncertainty" in msg.lower():
            hits += 1
            if hits == 1:
                print("FIRST HIT:\n" + msg, file=sys.stderr)
        else:
            other.append(msg.strip().splitlines()[0])
    except Exception as e:
        other.append(repr(e))
    finally:
        a.close(); b.close()

print(json.dumps({"attempts": ATTEMPTS, "uncertainty_errors": hits,
                  "clean_commits": ok, "other_errors": len(other),
                  "other_sample": other[:3]}, indent=2))
```

**Report:** the **hit rate over 100 attempts** (an empirical probability is a better
result than a single lucky screenshot), plus the verbatim first error message.

**Cross-check with the counter** — this works even if the scripted trigger never fires:

```sql
SELECT name, sum(value) FROM crdb_internal.node_metrics
WHERE name = 'txn.restarts.readwithinuncertainty' GROUP BY name;
```

Snapshot it before and after the script, and again before/after the P1 contention sweep.
A non-zero delta is direct evidence the mechanism is live in your cluster.

**If the hit rate is 0:** do not fake it. Report `INCONCLUSIVE` and reason about why —
the most likely cause is that A's first read already gave it an observed timestamp for
K2's leaseholder (check `SHOW RANGES`: are K1 and K2 really on ranges led by *different*
nodes?), or that the whole sequence took longer than `max_offset`. Try again with the
cluster restarted at `--max-offset=500ms` and K2 on a range led by n3 rather than n2.

**Interpretation:** this restart *is* the price of "no stale reads". Spanner pays the same
bill with commit-wait against TrueTime's error bounds; CockroachDB pays it lazily, on the
reader, only when a value happens to land in the window. Note the self-limiting property:
once `max_offset` has elapsed since a transaction began, it has no uncertainty left.

### K9 — Clock skew and `--max-offset`: an honest negative result

**Goal:** determine whether the max-offset safety mechanism can be exercised on this
topology. **Expected answer: no.** Record the reasoning — this is Threats-to-Validity
material, not a failure.

**Step 1 — observe the offset machinery working (it should, at ≈ 0):**

```sql
SELECT node_id, name, value FROM crdb_internal.node_metrics
WHERE name LIKE 'clock-offset%' ORDER BY node_id, name;
```
Also DB Console → Cluster → Runtime → *Clock Offset*. Screenshot it.

**Expected:** mean offset ≈ 0 ns, far below the 500 ms threshold. Of course it is — all
three nodes read the same `CLOCK_REALTIME` from the same kernel.

**Step 2 — record why fault injection is not available here.** Each of these fails for a
different, specific reason, and naming them is what makes this a finding rather than a
shrug:

| Approach | Why it does not work |
|---|---|
| `date -s` / `timedatectl` | Moves the host clock, so all three nodes move together. Relative offset stays 0. |
| `libfaketime` / `LD_PRELOAD` | Interposes on libc's `clock_gettime`. Go's runtime reads the clock through the **vDSO**, bypassing libc entirely, so the hook never fires for `time.Now()`. |
| Linux time namespaces (`unshare --time`) | Virtualise `CLOCK_MONOTONIC` and `CLOCK_BOOTTIME` only — **not** `CLOCK_REALTIME`, which is what the HLC's physical component uses. |
| Docker containers | Share the host kernel's clock. `CAP_SYS_TIME` lets a container change the *host* clock, i.e. all nodes at once. |

**R1 still applies:** if the operator wants to *try* one of these, let them, and report
what actually happened rather than what this table predicts.

**Step 3 — one thing you can test.** `--max-offset` must be identical cluster-wide. Try
starting a fourth node with a different value and record what happens:

```bash
cockroach start --insecure --store=$HOME/crdb/node4 \
  --listen-addr=localhost:26260 --http-addr=localhost:8083 \
  --locality=region=eu-west-1,zone=d --max-offset=250ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background
sleep 5; grep -iE 'offset|refus|mismatch|fatal' ~/crdb/node4/logs/cockroach.log | tail -20
```

**Do not predict the outcome.** Report the log. Then remove node4:
`cockroach node decommission 4 --insecure --host=localhost:26257` (or just kill it and
`rm -rf ~/crdb/node4` if it never joined).

**Step 4 — optional extension, if a VM or second machine is available.** This is the only
honest way to do real skew. Add a fourth node inside a VM (Multipass/VirtualBox/UTM), then
inside the VM:

```bash
sudo systemctl stop systemd-timesyncd chrony ntp 2>/dev/null
sudo date -s '+2 seconds'      # well beyond --max-offset=500ms
```

Then watch that node's log for the offset check and whether the process terminates itself.
**Only claim this if you did it.** If not, cite the documented behaviour and say plainly
that it was not verified here.

**Paper hook:** §3.5 and §Threats to Validity. Write it as: *"CockroachDB's correctness
depends on an operational assumption — that clock skew stays below `--max-offset` — which
the database enforces by terminating offending nodes. We could not exercise this on a
single-machine cluster, for the following structural reasons: ..."* An examiner will
respect that far more than a fabricated screenshot.

---

## 9. PHASE P — Performance and the Cost of Correctness

### P1 — The contention curve

**Goal:** show throughput as a function of concurrency at three levels of key-space
contention, using the workload generator bundled in the `cockroach` binary rather than a
shell loop.

```bash
cockroach workload run kv --help    # R3: confirm flag names on this build first
cockroach workload init kv 'postgresql://root@localhost:26257?sslmode=disable'
```

**Sweep.** `--cycle-length` is the number of distinct keys — that is your contention dial.
`--cycle-length=1` means every operation hits the same key.

```bash
for CYCLE in 1 10 100 100000; do
  for CONC in 1 2 4 8 16 32 64; do
    echo "=== cycle=$CYCLE conc=$CONC ==="
    cockroach workload run kv \
      --concurrency=$CONC --cycle-length=$CYCLE --read-percent=0 \
      --duration=60s --ramp=10s --display-every=10s \
      'postgresql://root@localhost:26257?sslmode=disable'
  done
done
```

Note `--ramp=10s` — discard the warm-up. Cold-start latency is consistently higher than
steady state and will skew a 60s run.

**Report:** ops/sec and p50/p99 vs concurrency, one line per `cycle-length`. Expected
shape: the `cycle-length=100000` line scales with concurrency; the `cycle-length=1` line
flattens or degrades, because a single key is a single Raft group with a single
leaseholder and no amount of concurrency parallelises it.

**Snapshot `txn.restarts.*` before and after each arm** — the restart mix tells you *which*
conflict mechanism is doing the limiting.

### P2 — SERIALIZABLE vs READ COMMITTED vs RC+FOR UPDATE — **the centrepiece**

**Goal:** quantify, simultaneously, what weaker isolation buys (throughput) and what it
costs (correctness). Most write-ups measure only the first half, which is why their
conclusion is always "READ COMMITTED is faster" — a claim that is true and useless.

**Design:**

- **Workload:** read-modify-write bank transfer. Read both balances, compute new values
  **in the client**, write them back. The cross-statement read→decide→write window is
  what makes lost updates possible; a single-statement `balance = balance - 10` would not
  discriminate between the levels at all (see I4).
- **Hot key space:** `--accounts 50`, not 10,000. With 10,000 accounts and random pairs,
  two concurrent transfers essentially never touch the same row, contention is ~0, and all
  three arms return identical numbers. **A benchmark without contention cannot compare
  concurrency-control strategies.** This is the single most common way this experiment is
  botched.
- **Oracle:** `sum(balance)`. Money must be conserved. This is the correctness axis.
- **Deterministic lock ordering** (touch the lower id first) so that deadlocks do not
  confound the retry statistics. C2 already covers deadlocks.

```python
#!/usr/bin/env python3
"""P2: throughput vs correctness across isolation levels.
Usage: p2.py --isolation serializable [--for-update] --accounts 50 --conc 16 --txns 2000
"""
import argparse, json, random, sys, time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import psycopg2
sys.path.insert(0, ".")
from harness import run_txn, summarize, write_csv   # §4.2

PORT = 26257
DSN = f"postgresql://root@localhost:{PORT}/seminar2?sslmode=disable"

def money():
    c = psycopg2.connect(DSN); c.autocommit = True
    with c.cursor() as cur:
        cur.execute("SELECT sum(balance), count(*) FROM accounts")
        r = cur.fetchone()
    c.close(); return r

def metrics():
    c = psycopg2.connect(DSN); c.autocommit = True
    with c.cursor() as cur:
        cur.execute("""SELECT name, sum(value) FROM crdb_internal.node_metrics
                       WHERE name LIKE 'txn.restarts%' GROUP BY name ORDER BY name""")
        r = dict(cur.fetchall())
    c.close(); return r

def one_transfer(iso, n_accounts, for_update):
    a = random.randint(1, n_accounts)
    b = random.randint(1, n_accounts)
    while b == a:
        b = random.randint(1, n_accounts)
    lo, hi = (a, b) if a < b else (b, a)
    lock = " FOR UPDATE" if for_update else ""

    def body(cur):
        # READ (ordered -> no deadlock)
        cur.execute(
            f"SELECT id, balance FROM accounts WHERE id IN (%s,%s) ORDER BY id{lock}",
            (lo, hi))
        bal = dict(cur.fetchall())
        # DECIDE, in the client, from the values we read. This window is the anomaly.
        new = {a: bal[a] - Decimal("10"), b: bal[b] + Decimal("10")}
        # WRITE (ordered -> no deadlock)
        for _id in (lo, hi):
            cur.execute("UPDATE accounts SET balance = %s WHERE id = %s", (new[_id], _id))
    return run_txn(PORT, iso, body)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--isolation", required=True)      # 'serializable' | 'read committed'
    p.add_argument("--for-update", action="store_true")
    p.add_argument("--accounts", type=int, default=50)
    p.add_argument("--conc", type=int, default=16)
    p.add_argument("--txns", type=int, default=2000)
    args = p.parse_args()

    label = args.isolation + ("+for_update" if args.for_update else "")
    m0, (sum0, n0) = metrics(), money()
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.conc) as ex:
        rows = list(ex.map(lambda _: one_transfer(args.isolation, args.accounts,
                                                  args.for_update),
                           range(args.txns)))
    wall = time.perf_counter() - t0
    m1, (sum1, n1) = metrics(), money()

    out = summarize(rows, label, {
        "isolation_requested": args.isolation,
        "for_update": args.for_update,
        "hot_accounts": args.accounts,
        "concurrency": args.conc,
        "wall_s": round(wall, 2),
        "throughput_txn_s": round(sum(r["outcome"] == "commit" for r in rows) / wall, 1),
        "money_before": str(sum0),
        "money_after": str(sum1),
        "money_delta": str(sum1 - sum0),          # MUST be 0 for a correct run
        "restart_deltas": {k: m1.get(k, 0) - m0.get(k, 0)
                           for k in set(m0) | set(m1)
                           if m1.get(k, 0) - m0.get(k, 0) != 0},
    })
    write_csv(f"results/data/p2_{label.replace(' ', '_')}.csv", rows)
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
```

**Run all three arms**, resetting `accounts` between each (SETUP-4):

```bash
mkdir -p results/data
python3 p2.py --isolation serializable   --accounts 50 --conc 16 --txns 2000
# reset.sql
python3 p2.py --isolation "read committed" --accounts 50 --conc 16 --txns 2000
# reset.sql
python3 p2.py --isolation "read committed" --for-update --accounts 50 --conc 16 --txns 2000
```

Then repeat the whole set **5 times** (R4) and report medians. Then sweep
`--conc ∈ {4, 16, 64}` to get a curve rather than a point.

**Hypotheses — state all four to the operator before they run it:**

| # | Prediction | Refuted if |
|---|---|---|
| H1 | SERIALIZABLE: `money_delta = 0`, high `txn.restarts.serializable` | money is lost |
| H2 | READ COMMITTED: `money_delta ≠ 0` — **money is destroyed** — with far fewer retries and higher throughput | the invariant holds |
| H3 | RC + FOR UPDATE: `money_delta = 0`, throughput between the other two | it loses money |
| H4 | RC + FOR UPDATE may be **slower than SERIALIZABLE**, because it takes exclusive locks where serializability would have needed none | it beats SERIALIZABLE |

**H4 is the interesting one.** Cockroach Labs argue exactly this in their ACIDRain
write-up — that overusing `FOR UPDATE` under READ COMMITTED can perform *worse* than just
using SERIALIZABLE. If your data supports it, you have empirically reproduced a claim from
the vendor's own engineering blog, and that is a genuinely strong result for a seminar
paper. If it does not, that is equally publishable — report it.

**The headline table for Chapter 4:**

| Arm | Throughput (txn/s) | p50 / p95 / p99 (ms) | Retries | **Money delta** |
|---|---|---|---|---|
| SERIALIZABLE | | | | **0.00** |
| READ COMMITTED | | | | **≠ 0** ← |
| RC + FOR UPDATE | | | | 0.00 |

That last column is the entire argument of the paper. Weaker isolation is not "a bit
faster"; it is faster *and* it silently violates an invariant the schema never declared.

### P3 — Client-side retry: strategies compared

**Goal:** turn the mandatory 40001 retry loop from a code listing into a measurement.

First, show the error shape deterministically:

```sql
SELECT crdb_internal.force_retry('500ms');
-- capture the full error text and SQLSTATE
```
This is a *unit-test* tool for exercising the retry path — it is **not** a load test.
Do not use it to "measure contention"; it fabricates errors rather than causing them.

Then, using the P2 workload at `--accounts 20 --conc 32` (high contention),
compare four strategies by swapping the `sleep` in `run_txn`:

| Strategy | Sleep |
|---|---|
| none | `max_retries = 1` |
| immediate | `0` |
| fixed | `0.05` |
| exponential + jitter | `min(0.05 * 2**(n-1), 1.0) * uniform(0.5, 1.5)` (the harness default) |

**Report:** success rate, p99 latency, and total attempts per committed transaction.
**Hypothesis:** immediate retry produces a retry storm — total attempts explode and p99
degrades — while exponential backoff with jitter converges. This is why the documented
pattern includes jitter, and now you can show it with numbers instead of asserting it.

**Also record:** which client libraries can retry transparently, and the important
asymmetry that CockroachDB can sometimes retry a transaction **server-side** without ever
telling the client — but only if it has not yet returned results. That is exactly the
property K8's script deliberately defeats, and noting the connection between P3 and K8
shows the examiner you understood the system rather than the tutorial.

---

## 10. `RESULTS.md` — output schema

After **every** experiment, append one block in exactly this shape. Show the operator the
block so they can paste it into the file. Do not deviate from the field names — the
consistency is what makes the file usable as paper source material later.

`RESULTS.md` opens with a header written once, at the end of PRE:

````markdown
# Results — Distributed Transactions & Consistency in CockroachDB

## Environment
- **Version:** <exact build tag from PRE-1>
- **Topology:** 3 nodes, single machine, loopback
- **Host:** <OS, CPU, RAM, disk type — ask the operator>
- **Localities:** n1 eu-west-1/a · n2 us-east-1/b · n3 us-west-1/c
- **--max-offset:** 500ms
- **License:** <set / not set>
- **Isolation gates:** sql.txn.read_committed_isolation.enabled=<v>, sql.txn.repeatable_read_isolation.enabled=<v>
- **Non-default cluster settings:** <paste PRE-6 output>
- **Protocol version:** 1.0
- **Protocol corrections applied:** <list every place the protocol was wrong; see R3>

## Invariant baseline
- accounts: <n> rows, sum(balance) = <x>
````

Then one block per experiment:

````markdown
---
## <ID> — <Title>

- **Run at:** <ISO-8601 local timestamp>
- **Sessions:** <e.g. A=n1, B=n2, M=n3>
- **Status:** `CONFIRMED` | `REFUTED` | `INCONCLUSIVE` | `NOT-REPRODUCIBLE-HERE`
- **Runs:** N=<n> (see §11 — one run is not a measurement)

### Hypothesis
<one sentence, stated before the run>

### Raw output
```
<verbatim paste. Do not edit, do not elide, do not tidy.
 If it is long, keep the salient 40 lines here and store the full dump at
 results/raw/<ID>.txt, referenced below.>
```
Full dump: `results/raw/<ID>.txt`

### Measurements
| metric | value |
|---|---|
| ... | ... |

### Interpretation
<Your reading. Names the specific mechanism (R7). Clearly separated from the raw
output above (R5). If the result refuted the hypothesis, say so explicitly and say
what the protocol got wrong.>

### Confidence
`High` | `Medium` | `Low` — because <reason>

### Caveats
<Anything that limits the claim: single machine, N too small, non-deterministic
outcome, setting changed mid-run, etc.>

### Paper hook
§<chapter>, <Figure/Table N>
````

**Rules for writing entries:**

- Append only. Never rewrite a past entry to match a later finding — if a later
  experiment overturns an earlier one, add a new entry and cross-reference it. The
  history of your understanding is part of the lab notebook.
- If the operator reports that a step errored, that is an entry too, with
  status `INCONCLUSIVE` and the error in `Raw output`.
- Every number that will appear in the paper must be traceable to an entry ID.

---

## 11. Analysis rules

### 11.1 Statistics

- **N ≥ 5** for any timed measurement. N ≥ 3 full repeats for any benchmark arm.
- Report **median and IQR** (or min/median/max). Never a bare mean — latency
  distributions are right-skewed and the mean is dominated by the tail.
- Report **p50, p95, p99** for latency, always together. p99 alone is noise at small N;
  p50 alone hides the thing that matters.
- **Discard warm-up.** Cold-start latency after an idle period is consistently higher
  than steady state. Use `--ramp=10s` for `cockroach workload`, and drop the first 10% of
  any harness run.
- **Never report throughput without the error count.** A run where every transaction
  aborted finishes fastest.
- Quote absolute numbers with units and with the settings they were produced under, or
  they are unfalsifiable.

### 11.2 Interpretation discipline

- If two arms differ by less than the run-to-run variance of a single arm, **the
  difference is not a result.** Say "no measurable difference at N=5", not "slightly
  faster".
- Do not attribute a latency difference to a mechanism you did not observe. If T2's trace
  shows two round trips and one round trip, you may talk about round trips. If you only
  have wall-clock, you may only talk about wall-clock.
- Distinguish three claims carefully, in this order of strength:
  1. "We measured X" (evidence)
  2. "X is consistent with mechanism M" (inference)
  3. "CockroachDB does M" (requires a citation, not your data)

### 11.3 When the protocol is wrong

It will be. Column names, metric names, setting names and exact error strings drift
between versions, and this document was written against documentation rather than against
your running cluster. When a step fails:

1. Run the discovery query for that object (§PRE-4, §PRE-5).
2. Adapt the step.
3. **Record the correction** in `RESULTS.md` → Environment → *Protocol corrections
   applied*.

That list of corrections is itself a small contribution and belongs in the paper's
methodology section.

---

## 12. ⛔ Claims you must not make

The operator is writing a paper that will be read by someone who knows this material. Each
of these is a specific, plausible, wrong sentence that this protocol's data does **not**
support. Check every draft paragraph against this list.

| ⛔ Do not write | ✅ Write instead |
|---|---|
| "CockroachDB is linearizable / strictly serializable." | "CockroachDB is serializable and guarantees no stale reads, but is not strictly serializable: it permits the *causal reverse* anomaly." |
| "Reads block because CockroachDB uses SERIALIZABLE." | "Reads block on uncommitted intents because of the consistency model, not the isolation level — K2 shows the block is identical at all three levels." |
| "CockroachDB uses two-phase commit." | "CockroachDB uses parallel commits, which merges 2PC's prepare and commit phases; the durable transaction record replaces the coordinator's log, which is why coordinator failure does not block (T4)." |
| "Follower reads are N ms faster." | "On a single-machine cluster follower reads are not faster; we measured *whether* a follower served the read via `kv.follower_reads.success_count` (K5) and found the staleness threshold." |
| "We reproduced the causal reverse anomaly." | "We reproduced the underlying mechanism (MVCC order diverging from start order, K3) and its `AS OF SYSTEM TIME` consequence (K4). Full causal reverse additionally requires inter-node clock skew, which a single-machine cluster cannot produce (K9)." |
| "CockroachDB's READ COMMITTED is PostgreSQL's READ COMMITTED." | "CockroachDB's READ COMMITTED is stronger than PostgreSQL's; and its REPEATABLE READ is snapshot isolation, not ANSI REPEATABLE READ." |
| "Uncertainty restarts are caused by badly synchronised clocks." | "Uncertainty restarts occur even with perfectly synchronised clocks: the interval reflects *possible* skew up to `--max-offset`, not measured skew (K8)." |
| "1PC is used for single-range transactions." | "1PC requires single-range **and** single-batch; an interactive `BEGIN…COMMIT` on one range may not qualify (T3)." |
| "A write intent is an exclusive lock." | Use the `lock_strength` value you actually observed in T1. A plain intent and a `FOR UPDATE` lock report differently (I5). |
| "The closed timestamp is 3 seconds." | "`kv.closed_timestamp.target_duration` was `<value>` in our cluster (PRE-6); K6 shows the follower-read threshold moves with it." |
| "SERIALIZABLE prevents all anomalies." | "SERIALIZABLE prevents all anomalies *defined by the ANSI isolation levels*. It says nothing about real-time ordering — that gap is what strict serializability closes." |
| "CockroachDB only offers SERIALIZABLE." | **Trap:** Cockroach Labs' own consistency-model blog post says this, but it **predates v23.2**. Since then READ COMMITTED (v23.2 preview, v24.1 GA) and REPEATABLE READ (v24.3.0, gated) exist. Cite that post for the *consistency model*, never for the isolation-level inventory. |
| "CockroachDB achieves X ops/sec." | "On this hardware, at this version, with these settings and this contention level, we measured X ops/sec." |
| "CAP explains this trade-off." | Prefer PACELC. CAP says nothing about the latency cost in the *absence* of a partition, which is exactly what K7 measures. |

---

## 13. Threats to validity — pre-written skeleton

Fill in and put this in the paper. Every item is real; do not soften them.

1. **Single machine.** All three nodes share one CPU, one page cache, one disk queue and
   one clock. Inter-node RTT is ~0. Consequently: (a) no latency result generalises to a
   deployed cluster; (b) resource contention between nodes is an unmeasured confound;
   (c) clock skew is 0 by construction, so K1's guarantee is confirmed but not stressed,
   and K9 could not be tested at all.
2. **No fault injection beyond process kill.** T4 tests one failure mode (clean
   `SIGKILL` of a gateway). Network partitions, disk stalls, slow nodes and clock jumps
   are untested. A partial partition is the failure mode most likely to expose
   consistency bugs, and it is exactly the one this topology cannot produce.
3. **Scale.** 10,000 rows, ~5 ranges, seconds-to-minutes of load. Range splits are manual
   and the merge queue is disabled. Nothing here says anything about behaviour at the
   scale CockroachDB is designed for.
4. **Version specificity.** v24.3.0 — the `.0` patch of an LTS series. Later v24.3.x
   patches fix bugs, including at least one affecting uniqueness enforcement under READ
   COMMITTED in regional-by-row tables. Results may not hold on other patches or majors.
5. **Contention is synthetic.** P2's 50-account hot set is chosen to *produce* contention,
   not to model a real workload. It answers "how do the isolation levels differ under
   contention", not "what will my application do".
6. **Client is Python + psycopg2 on the same host**, competing with the database for CPU.
   At high concurrency the client may be the bottleneck. Check: if throughput plateaus
   while database CPU is not saturated, suspect the client.
7. **Non-determinism.** I3 and C2 have non-deterministic winners; K3 and K8 are timing
   races with a hit rate below 1. Every such result is reported as a distribution over N
   runs, not as a single observation.
8. **Observer effect.** `SET tracing = on` (T2) adds overhead. Never take a latency
   measurement from a traced session.
9. **Licensing.** A throttled cluster degrades silently. All benchmark runs were verified
   against a licensed cluster (PRE-2); note the check in the methodology.

---

## 14. Mapping: experiments → paper chapters

| Chapter | Content | Evidence |
|---|---|---|
| 1 Introduction | Why distributed transactions are hard. **Use PACELC, not bare CAP** — CAP cannot express K7's finding, because there is no partition. | — |
| 2.1 ACID in distributed systems | **The two axes**: isolation (transaction interleavings) vs consistency (reads and real time); strict serializability as their conjunction. Fix the common muddle here, up front. | K2 |
| 2.2 Two-phase commit | 2PC, coordinator blocking, 3PC. Ancestry: Gray & Lamport's Paxos Commit — replicate the decision. | T4 (contrast) |
| 2.3 Isolation levels and anomalies | ANSI levels and why Berenson et al. showed them broken; Adya's phenomena; SI vs RR; SSI. | I1–I4 |
| 2.4 Consistency models | Linearizability (Herlihy & Wing), sequential, causal, eventual. Strict serializability. HLC (Kulkarni et al.) vs TrueTime. | K1, K3 |
| 2.5 Conflict detection | Pessimistic vs optimistic; timestamp ordering; write intents as the hybrid. | C1–C3 |
| 2.6 **Comparison (new)** | Table: CockroachDB / Spanner / YugabyteDB / TiDB / Calvin × {commit protocol, clock source, isolation levels, consistency guarantee, failure mode}. This serves the "consistency in distributed NoSQL" syllabus bullet far better than a generic theory section, and synthesis is what earns marks. | literature |
| 3.1 Transaction architecture | Gateway, intents, transaction record, HLC, **timestamp cache** (name it — most write-ups don't). | T1, T2 |
| 3.2 Parallel commits | Pipelining, staging, 1PC fast path, recovery. | T2, T3, T4 |
| 3.3 Isolation levels in CRDB | Three levels; v24.3.0 gating and **silent upgrade**; RC stronger than PostgreSQL's; RR = snapshot. | PRE-3, I1–I6 |
| 3.4 Conflict resolution | Lock table, wait queues, pushes, refresh spans, 40001 reason codes. | C1–C3, I3, I4 |
| 3.5 **Consistency model** | No stale reads; not strictly serializable; causal reverse; uncertainty intervals; `--max-offset`; closed timestamps; follower reads; GLOBAL tables. **This is the chapter the title promises.** | K1–K9 |
| 4 Experiments | Method, results, threats to validity. | all |
| 5 Conclusion | The trade in one sentence: no atomic clocks → cheaper writes → one anomaly and an operational clock assumption. K7 gives you the number. | — |

### Figures worth building

| # | Figure | From |
|---|---|---|
| 1 | Range/leaseholder map of `accounts` | SETUP-3 |
| 2 | Annotated trace excerpt: multi-range commit | T2 |
| 3 | Bar chart: Δcommits1PC vs Δparallelcommits × 4 transaction forms | T3 |
| 4 | Distribution of reader block time after coordinator kill | T4 |
| 5 | 3×4 anomaly matrix: {SER, RR, RC} × {non-repeatable, phantom, write skew, lost update} | I1–I4 |
| 6 | **Block duration vs isolation level** (three equal bars — the punchline) | K2 |
| 7 | Follower-read success rate vs staleness, two curves for two closed-timestamp settings | K5, K6 |
| 8 | **GLOBAL vs REGIONAL write latency at max-offset 500ms and 250ms** | K7 |
| 9 | Throughput vs concurrency × cycle-length | P1 |
| 10 | **The money table**: throughput / latency / retries / invariant delta × 3 arms | P2 |

Figures 6, 8 and 10 are the paper. If time runs short, cut others first.

---

## 15. References

Cite primary sources. The plan this replaces had one academic citation; that is the single
easiest thing to fix and the most visible.

### Foundational theory
- Papadimitriou, C. "The Serializability of Concurrent Database Updates." *JACM* 26(4), 1979.
- Herlihy, M. & Wing, J. "Linearizability: A Correctness Condition for Concurrent Objects." *ACM TOPLAS* 12(3), 1990.
- Lamport, L. "Time, Clocks, and the Ordering of Events in a Distributed System." *CACM* 21(7), 1978.
- Bernstein, P., Hadzilacos, V., Goodman, N. *Concurrency Control and Recovery in Database Systems.* Addison-Wesley, 1987. *(Legally free online — the best source for 2PC.)*

### Isolation levels — essential for Ch. 2.3
- Berenson, H., Bernstein, P., Gray, J., Melton, J., O'Neil, E., O'Neil, P. "A Critique of ANSI SQL Isolation Levels." *SIGMOD* 1995 (MSR TR-95-51). **CockroachDB's own documentation points readers here.** Non-negotiable.
- Adya, A. "Weak Consistency: A Generalized Theory and Optimistic Implementations for Distributed Transactions." PhD thesis, MIT, 1999. *(Portable, implementation-independent anomaly definitions.)*
- Fekete, A., Liarokapis, D., O'Neil, E., O'Neil, P., Shasha, D. "Making Snapshot Isolation Serializable." *ACM TODS* 30(2), 2005.
- Ports, D. & Grittner, K. "Serializable Snapshot Isolation in PostgreSQL." *VLDB* 2012. *(CockroachDB implements SSI too — the direct lineage of the refresh mechanism you observe in I3.)*
- Warszawski, T. & Bailis, P. "ACIDRain: Concurrency-Related Attacks on Database-Backed Web Applications." *SIGMOD* 2017. *(The empirical case against weak isolation + manual `FOR UPDATE` — i.e. P2's hypothesis H4.)*

### Commit protocols and consensus
- Gray, J. & Lamport, L. "Consensus on Transaction Commit." *ACM TODS* 31(1), 2006. **The direct intellectual ancestor of parallel commits.** Cite this in Ch. 2.2 and 3.2.
- Ongaro, D. & Ousterhout, J. "In Search of an Understandable Consensus Algorithm (Raft)." *USENIX ATC* 2014.
- Peng, D. & Dabek, F. "Large-scale Incremental Processing Using Distributed Transactions and Notifications (Percolator)." *OSDI* 2010. *(TiDB's model — the comparison arm.)*

### Distributed databases and clocks
- Corbett, J. et al. "Spanner: Google's Globally-Distributed Database." *OSDI* 2012. **The TrueTime contrast — the counterfactual for the entire paper.**
- Kulkarni, S., Demirbas, M., Madappa, D., Avva, B., Leone, M. "Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases." *OPODIS* 2014. **The HLC paper.** CockroachDB's clock is this; cite it, do not paraphrase a blog.
- Thomson, A. et al. "Calvin: Fast Distributed Transactions for Partitioned Database Systems." *SIGMOD* 2012. *(Deterministic ordering — the other design point.)*
- Bailis, P. et al. "Highly Available Transactions: Virtues and Limitations." *VLDB* 2014.
- Abadi, D. "Consistency Tradeoffs in Modern Distributed Database System Design (PACELC)." *IEEE Computer* 45(2), 2012.
- Gilbert, S. & Lynch, N. "Brewer's Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services." *SIGACT News* 33(2), 2002.

### CockroachDB primary sources
- Taft, R. et al. "CockroachDB: The Resilient Geo-Distributed SQL Database." *SIGMOD* 2020. **The one you must cite.**
- "A Demonstration of Multi-Region CockroachDB." *PVLDB* vol. 15, 2022 — https://www.vldb.org/pvldb/vol15/p3610-taft.pdf *(verify the author list from the PDF before citing)*. Directly relevant to K7.
- Kingsbury, K. "Jepsen: CockroachDB beta-20160829." https://jepsen.io/analyses/cockroachdb-beta-20160829 — §2.5 documents the causal reverse anomaly. **Cite this for K3/K4.**
- Jepsen, "Consistency Models." https://jepsen.io/consistency — the map for Ch. 2.4.
- Bailis, P. "Linearizability versus Serializability." http://www.bailis.org/blog/linearizability-versus-serializability/ — the two-axes framing for Ch. 2.1.
- Matei, A. "CockroachDB's consistency model." https://www.cockroachlabs.com/blog/consistency-model/ — *more than serializable, less than strictly serializable*; "no stale reads"; causal reverse; uncertainty intervals. **The single most important secondary source for Ch. 3.5.** ⚠️ Its isolation-level claims are stale — see §12.
- "How to talk about consistency and isolation in distributed DBs." https://www.cockroachlabs.com/blog/db-consistency-isolation-terminology/ — **the citation for K2.**
- "Living Without Atomic Clocks." https://www.cockroachlabs.com/blog/living-without-atomic-clocks — the HLC-vs-TrueTime rationale.
- "Parallel Commits." https://www.cockroachlabs.com/blog/parallel-commits/
- "Transaction Pipelining." https://www.cockroachlabs.com/blog/transaction-pipelining/
- "Isolation levels without the anomaly table." https://www.cockroachlabs.com/blog/232-read-committed-no-more-anomaly-tables/ — the argument that the anomaly table is the wrong teaching tool. Pairs with I4.
- "ACID Rain" (Cockroach Labs). https://www.cockroachlabs.com/blog/acid-rain/ — the `FOR UPDATE` performance claim behind P2/H4.
- Read Committed RFC. https://github.com/cockroachdb/cockroach/blob/master/docs/RFCS/20230122_read_committed_isolation.md — the design rationale, including the `AS OF SYSTEM TIME` promotion behind I6.
- Docs: Transaction Layer · Read Committed Transactions · Follower Reads · Multi-Region Overview · Licensing FAQs · **v24.3 Release Notes** (pin your claims to the version you ran).

---

## 16. Deliverables and repository

```
cockroachdb-distributed-transactions/
├── README.md                        # reproduce everything from a clean machine
├── PROTOCOL.md                      # this file
├── RESULTS.md                       # the lab notebook (§10)
├── paper/
│   └── seminar_paper_2.docx
├── presentation/
│   ├── presentation.pptx
│   └── casts/                       # asciinema recordings — see below
├── sql/
│   ├── 00_cluster_start.sh
│   ├── 01_preflight.sql
│   ├── 02_schema_seed.sql
│   ├── 03_splits.sql
│   ├── 04_reset.sql
│   ├── t1_write_intents.sql
│   ├── t2_tracing.sql
│   ├── t3_1pc_vs_parallel.sql
│   ├── t4_coordinator_failure.sql
│   ├── i1_non_repeatable_read.sql
│   ├── i2_phantom.sql
│   ├── i3_write_skew.sql
│   ├── i4_lost_update.sql
│   ├── i5_for_update.sql
│   ├── i6_rc_aost.sql
│   ├── c1_write_conflict.sql
│   ├── c2_deadlock.sql
│   ├── c3_priority_push.sql
│   ├── k3_mvcc_order.sql
│   ├── k4_aost_child_no_parent.sql
│   ├── k5_follower_reads.sql
│   ├── k6_closed_timestamp.sql
│   └── k7_global_tables.sql
├── scripts/
│   ├── harness.py                   # §4.2
│   ├── k1_no_stale_reads.py
│   ├── k2_block_by_isolation.py
│   ├── k8_uncertainty.py
│   ├── p1_contention_sweep.sh
│   ├── p2_isolation_benchmark.py
│   ├── p3_retry_strategies.py
│   └── netem_on.sh / netem_off.sh
├── results/
│   ├── raw/                         # verbatim terminal dumps, one per experiment ID
│   ├── data/                        # CSV from every measurement script
│   ├── figures/
│   └── screenshots/                 # DB Console
└── LICENSE
```

**Naming:** file names carry the experiment ID (`t3`, `k7`, `p2`), so every number in
`RESULTS.md` and every figure in the paper is traceable to the script that produced it.
A repo whose scripts stop at `exp8` while the protocol has nine experiments is the kind of
inconsistency a reviewer notices immediately.

### Presentation notes (10 minutes)

- **Do not run live demos.** Three live terminal demos in a 10-minute slot will overrun,
  and a wedged transaction on stage is unrecoverable. Record them with
  `asciinema rec casts/k2.cast`, embed as a player or an animated GIF, and keep the real
  cluster as a backup you never open.
- Budget **8 minutes of content for a 10-minute slot.** A schedule that sums to exactly
  10:00 with zero slack, and puts Q&A inside the last 30 seconds, has already failed.
- Suggested spine (≈8 min): title → the two axes (isolation vs consistency) → parallel
  commits vs 2PC → **K2 recording** (reads block at *every* isolation level) → **P2 money
  table** → **K7 latency vs max-offset** → not-strictly-serializable + causal reverse →
  conclusion. Three results, well told, beat ten bullet points.

---

## 17. Optional extensions

Only after everything above is in `RESULTS.md`.

- **E1 — Real clock skew.** Add a fourth node in a VM and `date -s '+2 seconds'`. Closes
  the K9 gap and turns a negative result into a positive one. Highest value per hour.
- **E2 — Real WAN latency.** Re-run K5/K7 on `cockroach demo --global --nodes 9
  --no-example-database --insecure`, which simulates inter-region latency between node
  localities. Note it is an in-memory, single-process demo cluster and marked
  experimental — a *complement* to the 3-node results, not a replacement, and say so.
- **E3 — Jepsen.** Run the CockroachDB Jepsen suite. Ambitious, and even a failed attempt
  documented honestly is a strong appendix.
- **E4 — TPC-C.** `cockroach workload run tpcc` gives a standard, citable workload with a
  built-in consistency check, instead of a bespoke one.
- **E5 — PostgreSQL contrast.** Run I1–I4 against local PostgreSQL. The same script, two
  databases, one table. Makes "CockroachDB's READ COMMITTED is stronger than PostgreSQL's"
  a measured claim rather than a quoted one — that is a real, small, original contribution
  and it costs about two hours.

---

## 18. Supervisor quick reference

Before you send the operator a step, check:

- [ ] Is this **one** step, with exact copy-pasteable commands?
- [ ] Did I state the hypothesis **and** the refutation condition first?
- [ ] Did I label every block `[A]` / `[B]` / `[M]` with its gateway node?
- [ ] Does it depend on a discovery step I have not run yet? (R3)
- [ ] Is it ⚠️ destructive — did I warn them and give the undo? (R8)
- [ ] Is N ≥ 5 for anything timed? (R4)
- [ ] For any isolation experiment: does it print `SHOW transaction_isolation`? (§1.3)

After they paste output:

- [ ] Did I put the raw output in `RESULTS.md` verbatim, unedited? (R5)
- [ ] Did the result actually match the hypothesis, or am I rounding toward it? (R1)
- [ ] Did I name a specific mechanism in the interpretation? (R7)
- [ ] Did I check the interpretation against the ⛔ list in §12?
- [ ] Am I about to state a number the operator never sent me? (R2)

**The failure mode to fear is not a broken experiment. It is a tidy, confident
`RESULTS.md` full of numbers nobody measured.**
