SELECT name, sum(value) FROM crdb_internal.node_metrics
WHERE name = 'txn.restarts.readwithinuncertainty' GROUP BY name;