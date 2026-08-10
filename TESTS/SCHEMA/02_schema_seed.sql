-- ============================================================================
-- 02_schema_seed.sql
-- Seminar 2 — Distributed Transactions & Consistency in CockroachDB v24.3.0
-- Implements protocol §PRE-2/PRE-3 (relevant cluster options), SETUP-1,
-- SETUP-2, SETUP-3. Protocol version 1.0.
--
-- Run against an INITIALIZED 3-node cluster:
--   cockroach sql --insecure --host=localhost:26257 --file=02_schema_seed.sql
--
-- Assumes the nodes were started WITH --locality and --max-offset=500ms
-- (start-time flags -- they cannot be set from SQL; see 00_cluster_start.sh)
-- and that `cockroach init` has already been run.
-- ============================================================================


-- ============================================================================
-- SECTION 0 -- Cluster options that belong at setup time (PRE-2, PRE-3,
-- SETUP-3). These are cluster-wide settings, not table options -- they
-- affect every session on the cluster, not just this one.
-- ============================================================================

-- --- 0a. LICENSE -- do this before anything else (protocol Sec 1.2) --------
-- A multi-node cluster with no key gets a 7-day grace period, then throttles.
-- READ COMMITTED, REPEATABLE READ, follower reads and multi-region features
-- are all licensed and will silently misbehave without a key. Get a free
-- Enterprise key (free for students / academic use) from the Cockroach Labs
-- Cloud Console, then uncomment and fill in BOTH lines below:
--
-- SET CLUSTER SETTING enterprise.license = 'PASTE-YOUR-KEY-HERE';
-- SET CLUSTER SETTING cluster.organization = 'PASTE-YOUR-UNIVERSITY-OR-NAME-HERE';
--
-- Verify once set:
-- SELECT name, value FROM [SHOW CLUSTER SETTINGS]
-- WHERE name IN ('enterprise.license','cluster.organization');

-- --- 0b. Isolation-level gates (PRE-3) --------------------------------------
-- Both default to a state where BEGIN TRANSACTION ISOLATION LEVEL READ
-- COMMITTED (or REPEATABLE READ) is accepted but silently runs as
-- SERIALIZABLE instead -- no error is raised. Turning these on now means
-- phase I is never blocked later. They don't affect the seeding statements
-- below; this is just the right place to set them once, up front.
SET CLUSTER SETTING sql.txn.read_committed_isolation.enabled = true;
SET CLUSTER SETTING sql.txn.repeatable_read_isolation.enabled = true;

-- --- 0c. Keep the merge queue from undoing the splits in Section 3 ---------
-- This one DOES matter for seeding: without it, CockroachDB will eventually
-- merge the small ranges created below back together in the background, and
-- a "distributed" transaction experiment can quietly degenerate into a
-- single-range one between sessions.
-- PROTOCOL CORRECTION (R3): kv.range_merge.queue_enabled is a deprecated
-- alias on this build; the preferred name is kv.range_merge.queue.enabled
-- (dot, not underscore, between queue and enabled). The alias still works
-- and only prints a NOTICE, but the current name avoids the noise.
SET CLUSTER SETTING kv.range_merge.queue.enabled = false;


-- ============================================================================
-- SECTION 1 -- Database + schema (SETUP-1)
-- No IF NOT EXISTS on the tables, deliberately: if this errors, you're
-- re-running against a cluster that already has this schema. Either skip to
-- Section 2 as needed, or start clean with: DROP DATABASE seminar2 CASCADE;
-- ============================================================================

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
-- Deliberately NO CHECK (balance >= 0): a CHECK constraint would mask lost
-- updates in P2 by rejecting the write that destroys money. The anomaly
-- needs to be observable, not prevented.

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
-- parent_id is deliberately NOT a foreign key: an FK would force the child
-- insert to read the parent row, which would make the two transactions
-- conflict, which would make serializability forbid the very reordering
-- K3 exists to demonstrate.
CREATE TABLE comments (
    id        INT PRIMARY KEY,
    parent_id INT NULL,
    body      STRING NOT NULL
);


-- ============================================================================
-- SECTION 2 -- Seed data (SETUP-2)
-- Row counts are load-bearing, not conservative placeholders -- see the
-- chat message for why more rows would not help (and would actively hurt
-- P2). Short version: this paper measures transaction MECHANISM, which
-- doesn't scale with row count; what the experiments need is CONTENTION,
-- which gets worse, not better, with more rows.
-- ============================================================================

INSERT INTO accounts (id, owner, balance, region)
SELECT g, 'user_' || g::STRING, 10000.00,
       (ARRAY['eu-west-1','us-east-1','us-west-1'])[((g-1) % 3) + 1]
FROM generate_series(1, 10000) AS g;

INSERT INTO inventory (product_id, name, stock)
SELECT g, 'product_' || g::STRING, 100 FROM generate_series(1, 1000) AS g;

INSERT INTO counters (id, name, value) VALUES (1, 'global_counter', 0);
INSERT INTO doctors (id, name, on_call) VALUES (1, 'Alice', true), (2, 'Bob', true);

-- comments is left EMPTY on purpose -- K3/K4 populate it as part of the
-- experiment itself; the insert order across two sessions IS the experiment.

-- Invariant baseline -- P2's "money delta" column is measured against this.
SELECT count(*) AS n_accounts, sum(balance) AS total_money FROM accounts;
-- expect: 10000, 100000000.00


-- ============================================================================
-- SECTION 3 -- Range topology (SETUP-3)
-- This is the real answer to "do we need more data": without this section,
-- all 10,000 accounts rows sit in ONE range (default max range size is
-- 512 MiB; 10k narrow rows are a few MB), so every "distributed" transaction
-- in phases T/C/K would silently run against a single range and a single
-- leaseholder -- T3 in particular would measure the opposite of its thesis.
-- Manual splits fix that deterministically, in milliseconds, at any row
-- count -- millions of rows would eventually split automatically too, just
-- at unpredictable boundaries you can't target, for no experimental benefit.
-- ============================================================================

ALTER TABLE accounts SPLIT AT VALUES (2001), (4001), (6001), (8001);
ALTER TABLE accounts SCATTER;

ALTER TABLE comments SPLIT AT VALUES (2);
ALTER TABLE comments SCATTER;

-- Verify -- do not proceed to phase T until BOTH of these are true:
--   1. >= 5 ranges for accounts
--   2. id=1 and id=9000 have DIFFERENT leaseholders
-- (v23.1+ needs WITH DETAILS for leaseholder info; if this errors on your
-- build, drop WITH DETAILS, run SHOW COLUMNS instead, and note the columns.)
SHOW RANGES FROM TABLE accounts WITH DETAILS;
SHOW RANGES FROM TABLE comments WITH DETAILS;

-- PROTOCOL CORRECTION (R3): a WHERE start_key <= '/1' AND end_key > '/1'
-- lookup does NOT work on this build -- '/1' never matches, because the
-- real pretty-printed key is prefixed with /Table/<oid>/<index>/..., not a
-- bare '/1'. String-matching a pretty-printed key is fragile in general, so
-- don't try to fix the literal -- since the splits below sit at known
-- integer boundaries, just bucket by id instead and read the leaseholder
-- straight off the SHOW RANGES output (rows come back key-ordered, so this
-- is a simple visual lookup at this scale):
--   id <  2001              -> range starting at TableMin
--   2001 <= id <  4001      -> next range
--   4001 <= id <  6001      -> next range
--   6001 <= id <  8001      -> next range
--   id >= 8001              -> last range before the comments boundary
-- Confirmed on this cluster: id=1 -> range 70 -> n2. id=9000 -> range 74 -> n1.

-- If leaseholders come out co-located after SCATTER (it's randomised),
-- just re-run: ALTER TABLE accounts SCATTER;


-- ============================================================================
-- SECTION 4 (OPTIONAL -- NOT part of the protocol) -- bulk scale-up variant
-- Uncomment only if you have a specific, separate reason to explore data
-- VOLUME (e.g. a rebalancing/compaction question, or as a base for the
-- TPC-C extension in Sec 17/E4). Not needed for phases T/I/C/K, and
-- actively HARMFUL to P2 -- never point P2's --accounts flag at this bigger
-- table. Adjust the upper bound of generate_series to control row count.
-- ============================================================================

-- INSERT INTO accounts (id, owner, balance, region)
-- SELECT g, 'user_' || g::STRING, 10000.00,
--        (ARRAY['eu-west-1','us-east-1','us-west-1'])[((g-1) % 3) + 1]
-- FROM generate_series(10001, 2000000) AS g;   -- adjust upper bound as desired
--
-- -- keep the invariant honest if you do this:
-- SELECT count(*) AS n_accounts, sum(balance) AS total_money FROM accounts;
-- -- with 2,000,000 total accounts: expect 2000000, 20000000000.00
--
-- -- and add more split points so the new rows aren't one giant unsplit range:
-- -- ALTER TABLE accounts SPLIT AT VALUES (50000),(200000),(500000),(1000000),(1500000);
-- -- ALTER TABLE accounts SCATTER;


-- ============================================================================
-- SECTION 5 -- Sanity check before moving on to phase T
-- ============================================================================

SELECT 'accounts'  AS table_name, count(*) AS n FROM accounts
UNION ALL SELECT 'inventory', count(*) FROM inventory
UNION ALL SELECT 'counters',  count(*) FROM counters
UNION ALL SELECT 'doctors',   count(*) FROM doctors
UNION ALL SELECT 'comments',  count(*) FROM comments;
-- expect: accounts 10000 * inventory 1000 * counters 1 * doctors 2 * comments 0

SELECT sum(balance) AS total_money FROM accounts;  -- expect 100000000.00
