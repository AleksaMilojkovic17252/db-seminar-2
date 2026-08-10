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
            verified = cur.fetchone()[0]              # PROOF (see protocol Sec 1.3)

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
