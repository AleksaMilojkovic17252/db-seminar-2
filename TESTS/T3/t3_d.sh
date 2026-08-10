#!/usr/bin/env bash
{
echo "=== BEFORE ==="
for port in 26257 26258 26259; do
  echo "--- port $port ---"
  cockroach sql --insecure --host=localhost:$port --database=seminar2 -e \
    "SELECT name, value FROM crdb_internal.node_metrics WHERE name IN ('txn.commits','txn.commits1PC','txn.parallelcommits') ORDER BY name;"
done

for i in $(seq 1 20); do
  cockroach sql --insecure --host=localhost:26257 --database=seminar2 -e "
    BEGIN;
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    UPDATE accounts SET balance = balance + 100 WHERE id = 9000;
    COMMIT;
  "
done

echo "=== AFTER ==="
for port in 26257 26258 26259; do
  echo "--- port $port ---"
  cockroach sql --insecure --host=localhost:$port --database=seminar2 -e \
    "SELECT name, value FROM crdb_internal.node_metrics WHERE name IN ('txn.commits','txn.commits1PC','txn.parallelcommits') ORDER BY name;"
done
} > t3_arm_d_output.txt
