"""K8: provoke ReadWithinUncertaintyIntervalError on a zero-skew cluster.

Recipe:
  A (gateway n1) begins, reads key K1 -> fixes A's timestamp, records an observed
    timestamp for n1 only.
  B (gateway n2) writes key K2 -> commits at a timestamp just above A's.
  A reads K2, whose leaseholder A has never contacted -> the value falls in A's
    uncertainty window -> restart error.
All three steps must fit inside max_offset (500ms). A script does; a human does not.

K1 and K2 MUST be on different ranges with different leaseholders (see SETUP-3),
and A's first read must have returned rows to the client, so CockroachDB cannot
transparently retry the transaction server-side and must surface the error.
"""
import psycopg2, psycopg2.errors, json, sys, time

K1, K2 = 1, 9000          # verify with SHOW RANGES that these differ (SETUP-3)
ATTEMPTS = 100

hits, other, ok = 0, [], 0
window_ms = []
for i in range(ATTEMPTS):
    # NOTE: psycopg2 issues BEGIN implicitly on the first statement of a non-autocommit
    # connection. Do NOT also execute BEGIN/COMMIT by hand here -- that raises
    # "there is already a transaction in progress" and every attempt lands in
    # other_errors, which looks exactly like "the experiment didn't fire".
    a = psycopg2.connect("postgresql://root@localhost:26259/seminar2?sslmode=disable")  # n3 -- holds NEITHER K1 nor K2's lease
    b = psycopg2.connect("postgresql://root@localhost:26258/seminar2?sslmode=disable")
    b.autocommit = True
    try:
        # Optional: flush results to the client so CockroachDB cannot transparently
        # retry the txn server-side and hide the error. Set it outside a txn.
        # Verify it exists on this build (SHOW ALL); drop this block if not.
        a.autocommit = True
        try:
            with a.cursor() as cur:
                cur.execute("SET results_buffer_size = 0")
        except Exception:
            pass
        a.autocommit = False

        with a.cursor() as cur:                  # implicit BEGIN: A's timestamp is fixed here
            t0 = time.perf_counter()
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K1,))
            cur.fetchall()                       # results returned -> no silent server-side retry
        with b.cursor() as cur:                  # B writes K2 at a slightly higher ts
            cur.execute("UPDATE accounts SET balance = balance + 0.01 WHERE id = %s", (K2,))
        with a.cursor() as cur:                  # K2's leaseholder is a node A has not contacted
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (K2,))
            cur.fetchall()
        window_ms.append(round((time.perf_counter() - t0) * 1000, 2))
        a.commit()
        ok += 1
    except psycopg2.errors.SerializationFailure as e:
        msg = str(e)
        if "uncertainty" in msg.lower():
            hits += 1
            if hits == 1:
                print("FIRST HIT:\n" + msg, file=sys.stderr)
        else:
            other.append(msg.strip().splitlines()[0])
    except Exception as e:
        other.append(repr(e))
    finally:
        a.close(); b.close()

print(json.dumps({"attempts": ATTEMPTS, "uncertainty_errors": hits,
                  "clean_commits": ok, "other_errors": len(other),
                  "other_sample": other[:3],
                  "window_ms_min": min(window_ms) if window_ms else None,
                  "window_ms_median": sorted(window_ms)[len(window_ms)//2] if window_ms else None,
                  "window_ms_max": max(window_ms) if window_ms else None}, indent=2))
