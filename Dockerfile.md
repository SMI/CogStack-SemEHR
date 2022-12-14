# Annotation Server in Docker

Creates a docker image with a postgres database populated with the
UMLS tables and a small set of sample document annotations.
When a container is started from this image it runs the webserver
on port 8080 behind an nginx proxy listening on port 8485.
If you map this to local port 8485 then you can query
the database via a web browser pointed to: https://localhost:8485/vis/

# Preparation

To build the docker image you need the SmiServices wheel, a couple of
postgres loading scripts, the umls CSV files, and some sample documents.

```
cp ../SmiServices/src/common/Smi_Common_Python/dist/SmiServices-4.0.0-py3-none-any.whl tmp
cp ../structuredreports/src/tools/postgres_init_01.sh    tmp
cp ../structuredreports/src/tools/semehr_to_postgres.py  tmp
mkdir -p  tmp/txt  tmp/meta  tmp/json
cp ../structuredreports/src/data/mtsamples_ihi_docs/doc000?.txt   tmp/txt
cp ../structuredreports/src/data/mtsamples_ihi_meta/doc000?.json  tmp/meta
cp ../structuredreports/src/data/mtsamples_ihi_semehr_results/doc000?.json  tmp/json
cat << _EOF > tmp/default.yaml
PostgresDatabases:
    SemEHRStoreOptions:
        HostName: 'localhost'
        UserName: 'semehr'
        Password: 'semehr'
        DatabaseName: 'semehr'
_EOF
```

Edit the URL at which you expect the service to run. Inside docker it should
be localhost:8080.  Edit the file `RESTful_service/vis/js/api.js`
```
service_url: "http://localhost:8080/api"
```

Check if you want a password by editing the file `RESTful_service/conf/settings.json`
```
  "passphrase": "something",
```

# Build

Building the image involves populating a postgres database so it will take
some time.

```
docker build -t howff/annotation_server .
```

# Run interactive for testing

This drops you into a shell; you can see /CogStack-SemEHR directory.
If postgres is not running see the Dockerfile for how to start it.

```
docker run -it --rm -p 8080:8080 howff/annotation_server /bin/bash
```

# Run live web server

You won't be able to CTRL-C out of this, use docker stop to terminate.
```
docker run --rm -p 8485:8485 howff/annotation_server
```

Test the live web server (should use SSL on port 8485)
```
curl -D /dev/tty -k https://localhost:8485/vis/
```

# Publish

```
docker login
docker push howff/annotation_server
```

