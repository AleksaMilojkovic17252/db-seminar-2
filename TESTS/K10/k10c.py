import psycopg2, json, time

w = psycopg2.connect("postgresql://root@localhost:26257/seminar2?sslmode=disable"); w.autocommit = True
r = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable"); r.autocommit = True

print("settling for 8s so the reset itself clears the closed-timestamp window...")
time.sleep(8)

N, mr_violations = 500, 0
trace = []
for i in range(N):
    with w.cursor() as cur:
        cur.execute("UPDATE counters SET value = %s WHERE id = 1", (i,))
    with r.cursor() as cur:
        cur.execute("SELECT value FROM counters WHERE id = 1")               # strong: sees i
        strong = cur.fetchone()[0]
        cur.execute("""SELECT value FROM counters
                       AS OF SYSTEM TIME follower_read_timestamp()
                       WHERE id = 1""")                                       # follower: older
        follower = cur.fetchone()[0]
    if follower > strong:               # read went "forward then backward" -> non-monotonic
        mr_violations += 1
    trace.append({"i": i, "strong": strong, "follower": follower})

print(json.dumps({
    "pairs": N,
    "mr_violations_detected": mr_violations,
    "trace": trace,
    "note": "follower<strong is expected staleness; we count follower>strong which "
            "cannot happen -> should be 0.",
}, indent=2))
