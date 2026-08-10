#!/usr/bin/env python3
"""P2 full protocol: 5x repeat of the 3-arm set at conc=16 (for medians, R4),
plus a concurrency sweep at conc in {4, 64} (conc=16 already covered by the
repeats above, so it isn't duplicated). Resets between every single run."""
import subprocess, json, psycopg2

DSN = "postgresql://root@localhost:26257/seminar2?sslmode=disable"
ARMS = [
    {"label": "serializable", "args": ["--isolation", "serializable"]},
    {"label": "read committed", "args": ["--isolation", "read committed"]},
    {"label": "read committed+for_update", "args": ["--isolation", "read committed", "--for-update"]},
]

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

def run_arm(extra_args, conc):
    cmd = ["python3", "p2.py", "--accounts", "50", "--conc", str(conc), "--txns", "2000"] + extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "could not parse JSON", "stdout": proc.stdout, "stderr": proc.stderr}

all_results = {"repeats": [], "sweep": []}

for rep in range(1, 6):
    print(f"=== Repeat {rep}/5 (conc=16) ===", flush=True)
    for arm in ARMS:
        reset()
        r = run_arm(arm["args"], conc=16)
        r["repeat"] = rep
        all_results["repeats"].append(r)
        print(f"  {arm['label']}: money_delta={r.get('money_delta')} "
              f"throughput={r.get('throughput_txn_s')}", flush=True)
        with open("p2_full_results.json", "w") as f:
            json.dump(all_results, f, indent=2)

for conc in (4, 64):
    print(f"=== Sweep conc={conc} ===", flush=True)
    for arm in ARMS:
        reset()
        r = run_arm(arm["args"], conc=conc)
        r["repeat"] = "sweep"
        all_results["sweep"].append(r)
        print(f"  {arm['label']} @conc={conc}: money_delta={r.get('money_delta')} "
              f"throughput={r.get('throughput_txn_s')}", flush=True)
        with open("p2_full_results.json", "w") as f:
            json.dump(all_results, f, indent=2)

print("P2 FULL PROTOCOL COMPLETE")
