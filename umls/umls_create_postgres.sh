#!/bin/bash

DB="semehr"
SCH="umls"

sudo -u postgres psql ${DB} -c "DROP TABLE IF EXISTS ${SCH}.cui;"
sudo -u postgres psql ${DB} -c "DROP TABLE IF EXISTS ${SCH}.rel;"
sudo -u postgres psql ${DB} -c "DROP TABLE IF EXISTS ${SCH}.snomed;"
sudo -u postgres psql ${DB} -c "DROP TABLE IF EXISTS ${SCH}.sty;"
sudo -u postgres psql ${DB} -c "DROP SCHEMA IF EXISTS ${SCH};"

# Create the schema
sudo -u postgres psql ${DB} -c "CREATE SCHEMA ${SCH} AUTHORIZATION semehr_admin;"

# Create tables and indexes
sudo -u postgres psql ${DB} -c "CREATE TABLE ${SCH}.cui(cui varchar(16), tui varchar(99), tuigroup varchar(99), cuilabel text);"
sudo -u postgres psql ${DB} -c "CREATE INDEX icui ON ${SCH}.cui (cui);"
sudo -u postgres psql ${DB} -c "CREATE TABLE ${SCH}.rel(cui1 varchar(16), has varchar(4), cui2 text);"
sudo -u postgres psql ${DB} -c "CREATE INDEX icui1 ON ${SCH}.rel (cui1);"
sudo -u postgres psql ${DB} -c "CREATE TABLE ${SCH}.snomed(snomed text, cui text NOT NULL);"
sudo -u postgres psql ${DB} -c "CREATE INDEX isnomed ON ${SCH}.snomed (snomed);"
sudo -u postgres psql ${DB} -c "CREATE TABLE ${SCH}.sty(tui varchar(8), tuigroup varchar(8), tuigrouplabel varchar(99));"
sudo -u postgres psql ${DB} -c "CREATE INDEX isty ON ${SCH}.sty (tui);"

# Allow access to schema
sudo -u postgres psql ${DB} -c "GRANT USAGE ON SCHEMA ${SCH} TO semehr_user;"
sudo -u postgres psql ${DB} -c "GRANT USAGE,CREATE ON SCHEMA ${SCH} TO semehr_admin;"

# Allow access to tables
sudo -u postgres psql ${DB} -c "GRANT SELECT ON ALL TABLES IN SCHEMA ${SCH} TO semehr_user;"
sudo -u postgres psql ${DB} -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${SCH} TO semehr_admin;"

# Allow access to future tables
sudo -u postgres psql ${DB} -c "ALTER DEFAULT PRIVILEGES FOR ROLE semehr_admin IN SCHEMA ${SCH} GRANT SELECT ON TABLES TO semehr_user;"
sudo -u postgres psql ${DB} -c "ALTER DEFAULT PRIVILEGES FOR ROLE semehr_admin IN SCHEMA ${SCH} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO semehr_admin;"

# Load data (use a fake quote char)
dir=$(pwd)
echo "$(date) Loading cui"
sudo -u postgres psql ${DB} -c "COPY ${SCH}.cui(cui, tui, tuigroup, cuilabel) FROM '${dir}/cui.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading rel"
sudo -u postgres psql ${DB} -c "COPY ${SCH}.rel(cui1, has, cui2) FROM '${dir}/rel.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading snomed"
sudo -u postgres psql ${DB} -c "COPY ${SCH}.snomed(snomed, cui) FROM '${dir}/snomed.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading sty"
sudo -u postgres psql ${DB} -c "COPY ${SCH}.sty(tui, tuigroup, tuigrouplabel) FROM '${dir}/sty.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Done"
