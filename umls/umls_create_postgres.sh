#!/bin/bash
# Create the umls schema and tables cui, rel, snomed, sty
# and populate them from the CSV files in this directory.
# You must have run umls_to_csv.py first.

# If you have got postgres installed locally set docker=False
# If you are using postgres in a separate docker container
# it must have been run with -e POSTGRES_PASSWORD=semehr.
docker=True

DB="semehr"
SCH="umls"

# If using docker (with -e POSTGRES_PASSWORD=semehr)
if [ $docker == "True" ]; then
    export PGPASSWORD="semehr" 
    CONNECTION="-h localhost -U postgres"
    COPY="\COPY"
else
    AUTH="sudo -u postgres"
    COPY="COPY"
fi

echo "$(date) Dropping old tables"
$AUTH psql $CONNECTION ${DB} -c "DROP TABLE IF EXISTS ${SCH}.cui;"
$AUTH psql $CONNECTION ${DB} -c "DROP TABLE IF EXISTS ${SCH}.rel;"
$AUTH psql $CONNECTION ${DB} -c "DROP TABLE IF EXISTS ${SCH}.snomed;"
$AUTH psql $CONNECTION ${DB} -c "DROP TABLE IF EXISTS ${SCH}.sty;"
$AUTH psql $CONNECTION ${DB} -c "DROP SCHEMA IF EXISTS ${SCH};"

# Create the schema
echo "$(date) Create schema ${SCH}"
$AUTH psql $CONNECTION ${DB} -c "CREATE SCHEMA ${SCH} AUTHORIZATION semehr_admin;"

# Create tables and indexes
echo "$(date) Create tables and indexes"
$AUTH psql $CONNECTION ${DB} -c "CREATE TABLE ${SCH}.cui(cui varchar(16), tui varchar(99), tuigroup varchar(99), cuilabel text);"
$AUTH psql $CONNECTION ${DB} -c "CREATE INDEX icui ON ${SCH}.cui (cui);"
$AUTH psql $CONNECTION ${DB} -c "CREATE TABLE ${SCH}.rel(cui1 varchar(16), has varchar(4), cui2 text);"
$AUTH psql $CONNECTION ${DB} -c "CREATE INDEX icui1 ON ${SCH}.rel (cui1);"
$AUTH psql $CONNECTION ${DB} -c "CREATE TABLE ${SCH}.snomed(snomed text, cui text NOT NULL);"
$AUTH psql $CONNECTION ${DB} -c "CREATE INDEX isnomed ON ${SCH}.snomed (snomed);"
$AUTH psql $CONNECTION ${DB} -c "CREATE TABLE ${SCH}.sty(tui varchar(8), tuigroup varchar(8), tuigrouplabel varchar(99));"
$AUTH psql $CONNECTION ${DB} -c "CREATE INDEX isty ON ${SCH}.sty (tui);"

# Allow access to schema
echo "$(date) Allow access to schema"
$AUTH psql $CONNECTION ${DB} -c "GRANT USAGE ON SCHEMA ${SCH} TO semehr_user;"
$AUTH psql $CONNECTION ${DB} -c "GRANT USAGE,CREATE ON SCHEMA ${SCH} TO semehr_admin;"

# Allow access to tables
echo "$(date) Allow access to tables"
$AUTH psql $CONNECTION ${DB} -c "GRANT SELECT ON ALL TABLES IN SCHEMA ${SCH} TO semehr_user;"
$AUTH psql $CONNECTION ${DB} -c "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ${SCH} TO semehr_admin;"

# Allow access to future tables
echo "$(date) Allow access to future tables"
$AUTH psql $CONNECTION ${DB} -c "ALTER DEFAULT PRIVILEGES FOR ROLE semehr_admin IN SCHEMA ${SCH} GRANT SELECT ON TABLES TO semehr_user;"
$AUTH psql $CONNECTION ${DB} -c "ALTER DEFAULT PRIVILEGES FOR ROLE semehr_admin IN SCHEMA ${SCH} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO semehr_admin;"

# Load data (use a fake quote char)
dir=$(pwd)
echo "$(date) Loading cui"
$AUTH psql $CONNECTION ${DB} -c "${COPY} ${SCH}.cui(cui, tui, tuigroup, cuilabel) FROM '${dir}/cui.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading rel"
$AUTH psql $CONNECTION ${DB} -c "${COPY} ${SCH}.rel(cui1, has, cui2) FROM '${dir}/rel.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading snomed"
$AUTH psql $CONNECTION ${DB} -c "${COPY} ${SCH}.snomed(snomed, cui) FROM '${dir}/snomed.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Loading sty"
$AUTH psql $CONNECTION ${DB} -c "${COPY} ${SCH}.sty(tui, tuigroup, tuigrouplabel) FROM '${dir}/sty.csv' WITH CSV HEADER QUOTE E'\b' DELIMITER '|';"
echo "$(date) Done"
