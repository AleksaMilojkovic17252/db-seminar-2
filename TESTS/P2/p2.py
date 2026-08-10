import argparse, json, random, sys, time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import psycopg2
sys.path.insert(0, ".")
from harness import run_txn, summarize, write_csv

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

    # Explicit isolation proof for the whole run, per harness contract Sec 4.3:
    # isolation_verified is mandatory, or the run is INCONCLUSIVE. conn_for()
    # already verifies per-thread and raises SystemExit on any mismatch, so one
    # canary check up front is sufficient and unambiguous -- if this succeeds,
    # every worker thread either matches or the whole process would have aborted.
    from harness import conn_for
    canary = conn_for(PORT, args.isolation)
    with canary.cursor() as cur:
        cur.execute("SHOW transaction_isolation")
        isolation_verified = cur.fetchone()[0]

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
        "isolation_verified": isolation_verified,
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
