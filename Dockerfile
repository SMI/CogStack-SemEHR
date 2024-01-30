# Dockerfile to run SemEHR annotation server on port 8080 behing nginx SSL port 8485
FROM postgres:latest
LABEL Maintainer="howff"
WORKDIR /CogStack-SemEHR
RUN apt-get update && apt-get install -y build-essential cmake ninja-build python3-pip python3-dev cython3 pybind11-dev libre2-dev vim sudo
RUN pip install --break-system-packages urllib3 joblib psycopg2_binary pymongo pyyaml mysql_connector_python pyre2 pydicom pika deepmerge
COPY RESTful_service /CogStack-SemEHR/RESTful_service/
COPY tmp /CogStack-SemEHR/tmp/
COPY umls /CogStack-SemEHR/umls/
COPY utils.py /CogStack-SemEHR/utils.py
COPY tmp/SmiServices-5.4.0-py3-none-any.whl /CogStack-SemEHR/
RUN pip install --break-system-packages /CogStack-SemEHR/SmiServices-5.4.0-py3-none-any.whl
# /usr/lib/postgresql/14/bin/
RUN (su postgres -c "initdb -D /var/lib/postgresql/data2")
RUN (echo "host all all 0.0.0.0/0 trust" >> /var/lib/postgresql/data2/pg_hba.conf)
RUN (su postgres -c "pg_ctl -D /var/lib/postgresql/data2 -l /tmp/logfile start"; /CogStack-SemEHR/tmp/postgres_init_01.sh; cd /CogStack-SemEHR/umls; chmod go+r *.csv; ./umls_create_postgres.sh; SMI_LOGS_ROOT=/CogStack-SemEHR /CogStack-SemEHR/tmp/semehr_to_postgres.py -y /CogStack-SemEHR/tmp/default.yaml -t /CogStack-SemEHR/tmp/txt -j /CogStack-SemEHR/tmp/json -m /CogStack-SemEHR/tmp/meta; su postgres -c "pg_ctl -D /var/lib/postgresql/data2 stop")
RUN apt-get install -y nginx
RUN sudo openssl req -x509 -nodes -days 7300 -newkey rsa:2048 \
 -subj "/C=GB/ST=Scotland/L=Edinburgh/O=The University of Edinburgh/OU=EPCC/CN=10.0.2.135" \
 -keyout /etc/ssl/private/nginx.key -out /etc/ssl/certs/nginx.crt
COPY nginx.conf /etc/nginx/sites-available/semehr
RUN ln -sf ../sites-available/semehr /etc/nginx/sites-enabled/semehr && rm -f /etc/nginx/sites-enabled/default
CMD (service nginx start; su postgres -c "pg_ctl -D /var/lib/postgresql/data2 -l /tmp/logfile start"; cd RESTful_service; python3 webserver.py -p 8080)
