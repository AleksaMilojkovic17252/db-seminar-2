#!/usr/bin/env python3
"""P3: client-side retry strategy comparison.
Same read-modify-write transfer workload as P2, at --accounts 20 --conc 32
(deliberately high contention), varying only the retry sleep strategy.
SERIALIZABLE throughout -- this is specifically about SERIALIZABLE's 40001
retry loop, not an isolation-level comparison.
"""
import argparse, json, random, sys, time, threading
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import psycopg2
import psycopg2.errors

PORT = 26257
DSN = f"postgresql://root@localhost:{PORT}/seminar2?sslmode=disable"
_local = threading.local()

STRATEGIES = {
    "none":               {"max_retries": 1,  "sleep_fn": None},
    "immediate":          {"max_retries": 10, "sleep_fn": lambda a: 0},
    "fixed":              {"max_retries": 10, "sleep_fn": lambda a: 0.05},
    "exponential_jitter": {"max_retries": 10,
                            "sleep_fn": lambda a: min(0.05 * (2 ** (a - 1)), 1.0)
                                                   * random.uniform(0.5, 1.5)},
}

def conn_for():
    if not hasattr(_local, "conn"):
        c = psycopg2.connect(DSN)
        c.autocommit = False
        with c.cursor() as cur:
            cur.execute("SET default_transaction_isolation = 'serializable'")
            cur.execute("SET statement_timeout = '30s'")
        c.commit()  # same fix as harness.py -- commit before checking, not after
        with c.cursor() as cur:
            cur.execute("SHOW transaction_isolation")
            actual = cur.fetchone()[0]
        c.commit()
        if actual != "serializable":
            raise SystemExit(f"FATAL: expected serializable, session reports {actual!r}")
        _local.conn = c
    return _local.conn

def run_txn_strategy(body, max_retries, sleep_fn):
    c = conn_for()
    t0 = time.perf_counter()
    for attempt in range(1, max_retries + 1):
        try:
            with c.cursor() as cur:
                body(cur)
            c.commit()
            return {"outcome": "commit", "attempts": attempt,
                    "latency_s": time.perf_counter() - t0}
        except psycopg2.errors.SerializationFailure:
            c.rollback()
            if attempt == max_retries:
                return {"outcome": "retry_exhausted", "attempts": attempt,
                        "latency_s": time.perf_counter() - t0}
            if sleep_fn:
                time.sleep(sleep_fn(attempt))
        except Exception as e:
            c.rollback()
            return {"outcome": "error", "attempts": attempt,
                    "latency_s": time.perf_counter() - t0, "error": repr(e)}

def make_body(n_accounts):
    a = random.randint(1, n_accounts)
    b = random.randint(1, n_accounts)
    while b == a:
        b = random.randint(1, n_accounts)
    lo, hi = (a, b) if a < b else (b, a)
    def body(cur):
        cur.execute("SELECT id, balance FROM accounts WHERE id IN (%s,%s) ORDER BY id", (lo, hi))
        bal = dict(cur.fetchall())
        new = {a: bal[a] - Decimal("10"), b: bal[b] + Decimal("10")}
        for _id in (lo, hi):
            cur.execute("UPDATE accounts SET balance = %s WHERE id = %s", (new[_id], _id))
    return body

def summarize(rows, label):
    lat = sorted(r["latency_s"] for r in rows if r["outcome"] == "commit")
    def pct(p):
        return lat[min(int(len(lat) * p), len(lat) - 1)] * 1000 if lat else float("nan")
    commits = sum(r["outcome"] == "commit" for r in rows)
    total_attempts = sum(r["attempts"] for r in rows)
    return {
        "label": label,
        "n": len(rows),
        "commits": commits,
        "retry_exhausted": sum(r["outcome"] == "retry_exhausted" for r in rows),
        "errors": sum(r["outcome"] == "error" for r in rows),
        "success_rate": round(commits / len(rows), 4),
        "total_attempts": total_attempts,
        "attempts_per_commit": round(total_attempts / commits, 3) if commits else None,
        "p50_ms": round(pct(0.50), 2),
        "p95_ms": round(pct(0.95), 2),
        "p99_ms": round(pct(0.99), 2),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    p.add_argument("--accounts", type=int, default=20)
    p.add_argument("--conc", type=int, default=32)
    p.add_argument("--txns", type=int, default=2000)
    args = p.parse_args()

    strat = STRATEGIES[args.strategy]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.conc) as ex:
        rows = list(ex.map(
            lambda _: run_txn_strategy(make_body(args.accounts),
                                        strat["max_retries"], strat["sleep_fn"]),
            range(args.txns)))
    wall = time.perf_counter() - t0

    out = summarize(rows, args.strategy)
    out["wall_s"] = round(wall, 2)
    out["concurrency"] = args.conc
    out["hot_accounts"] = args.accounts
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
