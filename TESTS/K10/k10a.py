#!/usr/bin/env python3
import psycopg2, json

c = psycopg2.connect("postgresql://root@localhost:26257/seminar2?sslmode=disable")
c.autocommit = True

N, violations = 500, 0
for i in range(N):
    with c.cursor() as cur:
        cur.execute("UPDATE counters SET value = %s WHERE id = 1", (i,))   # my write
        cur.execute("SELECT value FROM counters WHERE id = 1")             # my read, strong
        v = cur.fetchone()[0]
    if v != i:
        violations += 1
        print(f"RYW VIOLATION: wrote {i}, read {v}")
print(json.dumps({"reads": N, "ryw_violations": violations, "mode": "strong"}))
