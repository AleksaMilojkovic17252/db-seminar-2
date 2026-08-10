#!/usr/bin/env bash

pkill -f 'cockroach start' ; sleep 2   # clear any stale/leftover processes first

if [ ! -d "$HOME/crdb/node1" ]; then
  echo "No existing store at ~/crdb -- bootstrapping a fresh cluster."
  mkdir -p "$HOME/crdb"
  FRESH=1
else
  echo "Existing store found at ~/crdb -- resuming, data left untouched."
  FRESH=0
fi

cockroach start --insecure \
  --store=$HOME/crdb/node1 --listen-addr=localhost:26257 --http-addr=localhost:8080 \
  --locality=region=eu-west-1,zone=a --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 \
  --log-dir=$HOME/crdb/node1/logs --background

cockroach start --insecure \
  --store=$HOME/crdb/node2 --listen-addr=localhost:26258 --http-addr=localhost:8081 \
  --locality=region=us-east-1,zone=b --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 \
  --log-dir=$HOME/crdb/node2/logs --background

cockroach start --insecure \
  --store=$HOME/crdb/node3 --listen-addr=localhost:26259 --http-addr=localhost:8082 \
  --locality=region=us-west-1,zone=c --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 \
  --log-dir=$HOME/crdb/node3/logs --background

if [ "$FRESH" -eq 1 ]; then
  cockroach init --insecure --host=localhost:26257
  echo "Cluster started + initialized. Admin UI: http://localhost:8080"
else
  echo "Cluster started. Admin UI: http://localhost:8080"
fi
