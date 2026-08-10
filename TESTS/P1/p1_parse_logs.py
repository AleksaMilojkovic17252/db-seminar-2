
import re, glob, json

rows = []
for path in sorted(glob.glob("p1_logs/*.log")):
    tag = path.split("/")[-1].replace(".log", "")
    with open(path) as f:
        lines = f.readlines()

    last_header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("_elapsed"):
            last_header_idx = i
    if last_header_idx is None or last_header_idx + 1 >= len(lines):
        rows.append({"tag": tag, "error": "could not find a data line after any header"})
        continue

    data_line = lines[last_header_idx + 1]
    nums = re.findall(r"[-+]?\d*\.?\d+", data_line)
    if len(nums) < 9:
        rows.append({"tag": tag, "error": f"unexpected line: {data_line.strip()!r}"})
        continue

    rows.append({
        "tag": tag,
        "elapsed_s": float(nums[0]), "errors": int(nums[1]), "ops_total": int(nums[2]),
        "ops_per_sec": float(nums[3]), "avg_ms": float(nums[4]),
        "p50_ms": float(nums[5]), "p95_ms": float(nums[6]),
        "p99_ms": float(nums[7]), "pmax_ms": float(nums[8]),
    })

with open("p1_parsed.json", "w") as f:
    json.dump(rows, f, indent=2)

for r in rows:
    print(r)
