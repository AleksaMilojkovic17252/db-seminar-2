import psycopg2, json

# id=9000 (r74, leaseholder n1 per SETUP-3) -- connect to n2, a follower for that range
PORTS = [26257, 26258, 26259]
TARGET_PORT = 26258   # n2 -- follower for id=9000's range
STALENESS = ["0", "100ms", "500ms", "1s", "2s", "3s", "4s", "5s", "10s"]

def snapshot_follower_reads():
    total = 0
    for p in PORTS:
        conn = psycopg2.connect(f"postgresql://root@localhost:{p}/seminar2?sslmode=disable")
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM crdb_internal.node_metrics WHERE name = 'follower_reads.success_count'")
            total += cur.fetchone()[0]
        conn.close()
    return total

conn = psycopg2.connect(f"postgresql://root@localhost:{TARGET_PORT}/seminar2?sslmode=disable")
conn.autocommit = True

results = []
for s in STALENESS:
    before = snapshot_follower_reads()
    with conn.cursor() as cur:
        for _ in range(50):
            if s == "0":
                cur.execute("SELECT balance FROM accounts WHERE id = 9000")
            else:
                cur.execute(f"SELECT balance FROM accounts AS OF SYSTEM TIME '-{s}' WHERE id = 9000")
    after = snapshot_follower_reads()
    results.append({"staleness": s, "delta_follower_reads": after - before})

print(json.dumps(results, indent=2))
threshold = next((r["staleness"] for r in results if r["delta_follower_reads"] > 0), None)
print(f"Minimum staleness with nonzero delta: {threshold}")
