# REFRESH FIRST

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
