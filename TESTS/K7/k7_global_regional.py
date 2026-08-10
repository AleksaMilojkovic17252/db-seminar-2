#!/usr/bin/env python3
import psycopg2, time, random, statistics, json

WRITER_PORT = 26257   # n1
READER_PORTS = {"n2": 26258, "n3": 26259}
N = 100

def connect(port):
    c = psycopg2.connect(f"postgresql://root@localhost:{port}/mrtest?sslmode=disable")
    c.autocommit = True   # single statement = its own implicit transaction, so the
    return c              # commit-wait (t_global's actual cost) is inside the timed call

def time_writes(conn, table, n=N):
    times = []
    for _ in range(n):
        rid = random.randint(1, 100)
        t0 = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET v = 'y' WHERE id = %s", (rid,))
        times.append(time.perf_counter() - t0)
    return times

def time_reads(conn, table, n=N):
    times = []
    for _ in range(n):
        rid = random.randint(1, 100)
        t0 = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(f"SELECT v FROM {table} WHERE id = %s", (rid,))
            cur.fetchone()
        times.append(time.perf_counter() - t0)
    return times

def summarize(times):
    s = sorted(times)
    return {
        "median_ms": round(statistics.median(s) * 1000, 2),
        "p95_ms": round(s[int(len(s) * 0.95)] * 1000, 2),
        "min_ms": round(s[0] * 1000, 2),
        "max_ms": round(s[-1] * 1000, 2),
    }

results = {}

w = connect(WRITER_PORT)
for table in ("t_global", "t_regional"):
    results[f"write_{table}_n1"] = summarize(time_writes(w, table))
w.close()

for name, port in READER_PORTS.items():
    r = connect(port)
    for table in ("t_global", "t_regional"):
        results[f"read_{table}_{name}"] = summarize(time_reads(r, table))
    r.close()

print(json.dumps(results, indent=2))
