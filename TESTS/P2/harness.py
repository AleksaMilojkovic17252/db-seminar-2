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
        c.commit()  # BUGFIX: close the priming transaction here. Without this,
                    # SET default_transaction_isolation runs inside the same
                    # implicit transaction it's trying to configure -- it only
                    # affects transactions that start AFTER this commit, so the
                    # SHOW check below must run in a fresh one to mean anything.
        with c.cursor() as cur:
            # PROOF, not trust: never rely on the SET having worked (see PRE-3)
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
