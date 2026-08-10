#!/usr/bin/env python3
# t4_recovery_timer.py -- times how long a new write to id=1 blocks after
# node1 (the coordinator for [A]'s abandoned transaction) is killed.
# Connects via n2, NOT n1 -- n1 is expected to be dead when this runs.
import psycopg2
import time

conn = psycopg2.connect(
    host="localhost", port=26258, dbname="seminar2", user="root"
)
conn.autocommit = True
cur = conn.cursor()

t0 = time.perf_counter()
cur.execute("UPDATE accounts SET balance = balance - 1 WHERE id = 1;")
t1 = time.perf_counter()

print(f"Blocked write resolved in {t1 - t0:.3f}s")

cur.close()
conn.close()