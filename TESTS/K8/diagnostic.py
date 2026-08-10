import psycopg2, decimal, json

K1, K2 = 1, 9000
ATTEMPTS = 5
MAX_OFFSET_NS = decimal.Decimal(500_000_000)  # 500ms in ns

rows = []
for i in range(ATTEMPTS):
    a = psycopg2.connect("postgresql://root@localhost:26259/seminar2?sslmode=disable")  # n3
    b = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable")
    b.autocommit = True
    a.autocommit = False
    try:
        with a.cursor() as cur:
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K1,))
            cur.fetchall()
            cur.execute("SELECT cluster_logical_timestamp()")
            t_a = cur.fetchone()[0]                       # A's fixed HLC timestamp
        with b.cursor() as cur:
            cur.execute("UPDATE accounts SET balance = balance + 0.01 WHERE id = %s", (K2,))
        with b.cursor() as cur:
            cur.execute(
                "SELECT crdb_internal_mvcc_timestamp FROM accounts WHERE id = %s", (K2,)
            )
            t_b = cur.fetchone()[0]                       # B's actual commit timestamp
        with a.cursor() as cur:
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K2,))
            cur.fetchall()
        a.commit()
        gap_ns = t_b - t_a
        rows.append({
            "attempt": i,
            "t_a": str(t_a),
            "t_b": str(t_b),
            "gap_ns": float(gap_ns),
            "gap_ms": round(float(gap_ns) / 1_000_000, 3),
            "within_uncertainty_window[0,500ms]": (
                decimal.Decimal(0) <= gap_ns <= MAX_OFFSET_NS
            ),
        })
    except Exception as e:
        rows.append({"attempt": i, "error": repr(e)})
    finally:
        a.close(); b.close()

print(json.dumps(rows, indent=2))
