#!/usr/bin/env python3
"""Runs all 4 P3 retry strategies in sequence, resetting accounts between each."""
import subprocess, json, psycopg2

DSN = "postgresql://root@localhost:26257/seminar2?sslmode=disable"
STRATEGIES = ["none", "immediate", "fixed", "exponential_jitter"]

def reset():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET balance = 10000.00 WHERE balance != 10000.00")
        cur.execute("UPDATE doctors SET on_call = true")
        cur.execute("UPDATE counters SET value = 0 WHERE id = 1")
        cur.execute("UPDATE inventory SET stock = 100, version = 1 WHERE stock != 100 OR version != 1")
        cur.execute("DELETE FROM comments")
        cur.execute("SELECT sum(balance) FROM accounts")
        s = cur.fetchone()[0]
    conn.close()
    assert str(s) == "100000000.00", f"reset did not converge, sum={s}"

results = []
for strat in STRATEGIES:
    print(f"=== {strat} ===", flush=True)
    reset()
    proc = subprocess.run(
        ["python3", "p3.py", "--strategy", strat, "--accounts", "20",
         "--conc", "32", "--txns", "2000"],
        capture_output=True, text=True,
    )
    try:
        r = json.loads(proc.stdout)
    except json.JSONDecodeError:
        r = {"error": "could not parse JSON", "stdout": proc.stdout, "stderr": proc.stderr}
    results.append(r)
    print(f"  success_rate={r.get('success_rate')} attempts_per_commit={r.get('attempts_per_commit')} "
          f"p99_ms={r.get('p99_ms')}", flush=True)
    with open("p3_results.json", "w") as f:
        json.dump(results, f, indent=2)

print("P3 COMPLETE")
