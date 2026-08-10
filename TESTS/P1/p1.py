#!/usr/bin/env python3
import subprocess, psycopg2, json, time, os

CYCLES = [1, 10, 100, 100000]
CONCS = [1, 2, 4, 8, 16, 32, 64]
DURATION = "60s"
RAMP = "10s"
DSN = "postgresql://root@localhost:26257?sslmode=disable"
OUTDIR = "p1_logs"
os.makedirs(OUTDIR, exist_ok=True)

def snapshot_restarts():
    total = {}
    for port in (26257, 26258, 26259):
        conn = psycopg2.connect(f"postgresql://root@localhost:{port}/seminar2?sslmode=disable")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, value FROM crdb_internal.node_metrics "
                "WHERE name LIKE 'txn.restarts%'"
            )
            for name, value in cur.fetchall():
                total[name] = total.get(name, 0) + value
        conn.close()
    return total

results = []
total_combos = len(CYCLES) * len(CONCS)
i = 0
for cycle in CYCLES:
    for conc in CONCS:
        i += 1
        tag = f"cycle{cycle}_conc{conc}"
        print(f"=== [{i}/{total_combos}] {tag} ===", flush=True)

        before = snapshot_restarts()
        t0 = time.time()
        proc = subprocess.run(
            ["cockroach", "workload", "run", "kv",
             f"--concurrency={conc}", f"--cycle-length={cycle}", "--read-percent=0",
             f"--duration={DURATION}", f"--ramp={RAMP}", "--display-every=10s",
             DSN],
            capture_output=True, text=True,
        )
        elapsed = time.time() - t0
        after = snapshot_restarts()

        with open(f"{OUTDIR}/{tag}.log", "w") as f:
            f.write(proc.stdout)
            f.write("\n--- STDERR ---\n")
            f.write(proc.stderr)

        deltas = {k: after.get(k, 0) - before.get(k, 0) for k in set(before) | set(after)}
        nonzero_deltas = {k: v for k, v in deltas.items() if v}
        results.append({
            "cycle": cycle, "conc": conc, "wall_s": round(elapsed, 1),
            "restart_deltas": nonzero_deltas, "log_file": f"{tag}.log",
        })
        with open("p1_results.json", "w") as f:
            json.dump(results, f, indent=2)

        print(f"  done in {elapsed:.1f}s, nonzero restart deltas: {nonzero_deltas}", flush=True)

print("SWEEP COMPLETE")
