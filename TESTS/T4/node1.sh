cockroach start --insecure \
  --store=$HOME/crdb/node1 --listen-addr=localhost:26257 --http-addr=localhost:8080 \
  --locality=region=eu-west-1,zone=a --max-offset=500ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background
