#!/usr/bin/env bash
cockroach start --insecure --store=$HOME/crdb/node4 \
  --listen-addr=localhost:26260 --http-addr=localhost:8083 \
  --locality=region=eu-west-1,zone=d --max-offset=250ms \
  --join=localhost:26257,localhost:26258,localhost:26259 --background
sleep 5; grep -iE 'offset|refus|mismatch|fatal' ~/crdb/node4/logs/cockroach.log | tail -20

#Start a mismatched node 

tail -60 ~/crdb/node4/logs/cockroach.log

#Check logs

cockroach node decommission 4 --insecure --host=localhost:26257

#cleanup