#!/usr/bin/env bash
pkill -f "cockroach start" && echo "Cluster stopped." || echo "No cockroach cluster was running."
