CREATE DATABASE mrtest;
ALTER DATABASE mrtest SET PRIMARY REGION 'eu-west-1';
ALTER DATABASE mrtest ADD REGION 'us-east-1';
ALTER DATABASE mrtest ADD REGION 'us-west-1';
SHOW REGIONS FROM DATABASE mrtest;
USE mrtest;

CREATE TABLE t_global   (id INT PRIMARY KEY, v STRING) LOCALITY GLOBAL;
CREATE TABLE t_regional (id INT PRIMARY KEY, v STRING) LOCALITY REGIONAL BY TABLE IN PRIMARY REGION;
INSERT INTO t_global   SELECT g, 'x' FROM generate_series(1,100) g;
INSERT INTO t_regional SELECT g, 'x' FROM generate_series(1,100) g;

SELECT variable, value FROM crdb_internal.cluster_settings
WHERE variable LIKE '%lead_for_global%' OR variable LIKE '%closed_timestamp%';

-- RUN SCRIPT

-- AFTER RUNNING THE SCRIPT, RESTART COCKROACHDB AND CHANGE --max-offset to 250ms AND RUN THE SCRIPT AGAIN
