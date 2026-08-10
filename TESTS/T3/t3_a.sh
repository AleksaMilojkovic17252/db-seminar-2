#!/usr/bin/env bash
{
echo "=== BEFORE ==="
for port in 26257 26258 26259; do
  echo "--- port $port ---"
  cockroach sql --insecure --host=localhost:$port --database=seminar2 -e \
    "SELECT name, value FROM crdb_internal.node_metrics WHERE name IN ('txn.commits','txn.commits1PC','txn.parallelcommits') ORDER BY name;"
done

for i in $(seq 1 20); do
  cockroach sql --insecure --host=localhost:26257 --database=seminar2 -e \
    "UPDATE accounts SET balance = balance + CASE id WHEN 1 THEN -100 ELSE 100 END WHERE id IN (1, 2);"
done

echo "=== AFTER ==="
for port in 26257 26258 26259; do
  echo "--- port $port ---"
  cockroach sql --insecure --host=localhost:$port --database=seminar2 -e \
    "SELECT name, value FROM crdb_internal.node_metrics WHERE name IN ('txn.commits','txn.commits1PC','txn.parallelcommits') ORDER BY name;"
done
} > t3_arm_a_output.txt
