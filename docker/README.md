# Separate Postgres and SemEHR

To run the SemEHR web server in its own container, with the database
held in an external postgres database (be that local, remote or in a container).
The semehr container will include nginx for handling HTTPS.

* Install postgres separately, on a different host or in a docker container.
Example docker instance:
```
docker run --name postgres -e POSTGRES_PASSWORD=password -d --rm -p 54320:5432 postgres:14
```

* If you don't have psql locally you can install `postgresql-client` or use a docker image:
```
docker build -t psqlclient -f Dockerfile_psql .
docker run --rm -it --entrypoint /bin/bash psqlclient
```

* Edit the postgres scripts with the correct hostname, port and password:
`CogStack-SemEHR/umls/umls_create_postgres.sh`
and
`StructuredReports/src/tools/postgres_init_01.sh`

* Build the SemEHR docker image. First copy the config file `CogStack-SemEHR/RESTful_service/conf/settings.json` into this directory and edit the postgres server settings then
```
docker build -t howff/semehr:2 -f Dockerfile2 --progress=plain .
```

* Run SemEHR:
```
docker run  -d -p 8485:8485 howff/semehr:2b
```

* Test that SemEHR is running
```
curl -k https://localhost:8485/vis/
```


* Create the SemEHR database. Ensure correct hostname, port, PGPASSWORD. May need to concatenate lines instead of using continuation characters
```
StructuredReports/src/tools/postgres_init_01.sh --docker
```

* Populate the UMLS data files in the database
```
cd CogStack-SemEHR/umls
tar xf umls_20210905.tar.xz
./umls_create_postgres.sh --docker
```

* Populate the sample documents in the database if you have no real documents, make sure to change the postgres config below:
```
cd StructuredReports/src/data
tar xf mtsamples_ihi_semehr_results.tar.xz
export SMI_LOGS_ROOT=/tmp
../tools/semehr_to_postgres.py \
 --pg-host localhost --pg-port 54320 --pg-user semehr --pg-pass semehr \
 -t mtsamples_ihi_docs -j mtsamples_ihi_semehr_results -m mtsamples_ihi_meta
```
