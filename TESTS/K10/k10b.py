import psycopg2, json

c = psycopg2.connect("postgresql://root@localhost:26257/seminar2?sslmode=disable")
c.autocommit = True

N, ryw_broken, saw_own = 500, 0, 0
for i in range(N):
    with c.cursor() as cur:
        cur.execute("UPDATE counters SET value = %s WHERE id = 1", (i,))    # my write, NOW
        # my read, but at a past (follower-safe) timestamp:
        cur.execute("""SELECT value FROM counters
                       AS OF SYSTEM TIME follower_read_timestamp()
                       WHERE id = 1""")
        v = cur.fetchone()[0]
    if v != i:
        ryw_broken += 1          # did NOT see my own just-committed write
    else:
        saw_own += 1
print(json.dumps({"reads": N, "ryw_broken": ryw_broken, "saw_own_write": saw_own,
                  "mode": "follower_read"}))
