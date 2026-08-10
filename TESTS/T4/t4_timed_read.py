#!/usr/bin/env python3
"""T4: time how long a reader on n2 blocks on id=1's intent after node1 is hard-killed.
Run this IMMEDIATELY after the kill -- the clock starts when this process connects."""
import psycopg2, time, json

c = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable")
c.autocommit = True
t0 = time.perf_counter()
with c.cursor() as cur:
    cur.execute("SELECT balance FROM accounts WHERE id = 1")
    v = cur.fetchone()[0]
print(json.dumps({"blocked_s": round(time.perf_counter() - t0, 3), "balance": str(v)}))
