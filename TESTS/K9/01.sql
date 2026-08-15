SELECT store_id, name, value FROM crdb_internal.node_metrics
WHERE name LIKE 'clock-offset%' ORDER BY store_id, name;

--AFTER THIS GO TO THE DASHBOARD AND LOOKG FOR DB Console -> Cluster -> Runtime -> Clock Offset

SELECT node_id, address, locality, is_live FROM crdb_internal.gossip_nodes ORDER BY node_id; --Check if Node 4 joined