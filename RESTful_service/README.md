# Structure Report Annotations Query Interface

## ChangeLog

- (25 August 2021) PostgreSQL backend, extra search fields in UI (not in API yet).
- (26 July 2021) Initial version for MongoDB backend UI. It contains two components:
    - a restful web service: listens to 8000 port
    - a web UI to query/visualise results (docs, annotations and texts)

## TODO
- [ ] UMLS semantics based subsumption inference for concept querying
      (query expansion)
      NOTE: ideally options to limit the depth of the expansion tree,
      and to exclude specified nodes from the sub-tree.
- [X] implement passphrase NOTE: the server should send a salt/seed
      which the client uses to hash the passphrase before sending it
      but that requires server session state.
      Do a simple hash at least so not plaintext.
- [ ] Document text content ** The field `redacted_text` is in each document, need to display it with annotations highlights (tooltips?).
- [X] Reduce to a single CSV file upload button (since multiple files can be attached that way)
- [ ] Implement search of document text NOTE: this is going to be fairly slow
- [X] Implement filter by modalities
- [ ] Post-search filtering by the uploaded files
      (cannot do this in SQL without passing a huge amount to the API, needs POST, defeats RESTful semantics)
- [ ] Don't allow PatientID to be retrieved
- [X] Implement multiple query terms
- [ ] Add more search terms to the web UI dynamically,
      https://mattstauffer.com/blog/a-little-trick-for-grouping-fields-in-an-html-form/
      and
      http://www.satya-weblog.com/2010/02/add-input-fields-dynamically-to-form-using-javascript.html
- [ ] the Machine Learning part for researchers to fine-tune results for their study

## Introduction

A search interface to the Structure Report annotations database.

To run it, `python3 webserver.py -p 8080`

Access the web page at `http://localhost:8080`

If you are accessing the server host through SSH then set up a tunnel, eg.
`ssh -L 8000:localhost:8000 user@host`

To run the webserver on a different port: `python3 ./webserver.py -p 8485`
but you also need to edit the client-side code in `vis/js/api.js`
which defaults to `service_url: "http://localhost:8000/api",`

If you are running behind nginx which is SSL on port 8485 you should use
port 8080 (see nginx.conf, and explanation below).

If you have an external IP address which is not available locally and you
need to test locally then
```
sudo ip link add eth10 type dummy
sudo ip addr add 10.0.2.135/32 brd + dev eth10 label eth10:0
```

## Installation

Create a symbolic link to `utils.py` in the parent directory.

Create a Python3 virtual environment and install the requirements:
```
pip install pymongo
pip install psycopg2_binary
```
This might require the dev versions of the postgresql client libs.

### External datasets

The UMLS downloads will require the user to sign an agreement.

See the umls directory for details on extraction of the UMLS database.

Load the CSV files into PostgreSQL tables, or if small enough just keep in RAM.
See the umls.py script for the memory option.

Currently the code requires these files in the `../umls` directory:
* rel.csv (mapping cui codes to children cui codes)
* snomed.csv (mapping snomed codes to cui codes)
* sty.csv (mapping semantic types to semantic type groups)

The files need to be loaded into PostgreSQL so use `./umls_create_postgres.sh`
in the `umls` directory.

## Configuration

The main configuration file is in `conf/settings.json`

You can configure the database access and choose between MongoDB and PostgreSQL
by changing `databaseBackend` between `postgreSQL` or `mongoDB`. Note that only
PostgreSQL has full support implemented right now (MongoDB queries will be slow).

The passphrase is also defined in here with the `passphrase` key.

The UMLS tables need to be defined in the settings.

Mappings are yet to be documented...

## Security

A passphrase can be required from the user if configured in the settings file.
This is passed as part of the URL so it is not very well hidden.
It is only used by the API so is not visible to the user but can be discovered.
It is hashed for obscurity.
If traffic is passed through HTTPS then the passphrase cannot be seen on the network.
There is no username, and only one passphrase, so no way to separate users
and no way to have different users with different roles (sets of permissions).

## Deployment

To deploy behind nginx proxy use a self-signed certificate.
Use this command to create one which expires in 20 years.
See: https://www.cloudsavvyit.com/1306/how-to-create-and-use-self-signed-ssl-on-nginx/

```
sudo openssl req -x509 -nodes -days 7300 -newkey rsa:2048 \
 -subj "/C=GB/ST=Scotland/L=Edinburgh/O=The University of Edinburgh/OU=EPCC/CN=10.0.2.135" \
 -keyout /etc/ssl/private/nginx.key -out /etc/ssl/certs/nginx.crt
```

If you might want to import this certificate into a client Windows computer then
export it in pfx format:

```
openssl pkcs12 -export -out semehr.pfx -inkey /etc/ssl/private/nginx.key -in /etc/ssl/certs/nginx.crt
```

Create `/etc/nginx/sites-available/semehr`

```
# Redirect to HTTPS
server {
    listen 80;
    server_name localhost;
    return 301 https://$host$request_uri;
}
# Listen on port 8485 and act as a proxy for port 8080
server {
    listen 8485 ssl http2; # HTTP/2 is only possible when using SSL
    server_name localhost;
    ssl_certificate /etc/ssl/certs/nginx.crt;
    ssl_certificate_key /etc/ssl/private/nginx.key;

    client_max_body_size 1024M;
    location / {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Host $host;
        proxy_send_timeout 6000s; # 100 minutes
        proxy_read_timeout 6000s; # 100 minutes
        #proxy_next_upstream_timeout 0; # no timeout
        #proxy_cache cache;
        #proxy_cache_bypass $cookie_auth_tkt;
        #proxy_no_cache $cookie_auth_tkt;
        #proxy_cache_valid 30m;
        #proxy_cache_key $host$scheme$proxy_host$request_uri;
        # In emergency comment out line to force caching
        # proxy_ignore_headers X-Accel-Expires Expires Cache-Control;
    }
}
```

Make a symlink to it from `/etc/nginx/sites-enabled/semehr`
Don't forget to remove the default site.
```
ln -s ../sites-available/semehr /etc/nginx/sites-enabled/semehr
rm -f /etc/nginx/sites-enabled/default
systemctl reload nginx
```

You can test like this (note https, note port 8485, note -k to ignore self-signed cert):
```
curl -D /dev/tty -k https://localhost:8485/vis/
```

To run as a system service create `/etc/systemd/system/semehr.service`
```
[Unit]
Description=SemEHR Annotation Server

[Service]
Type=simple
WorkingDirectory=/opt/semehr/CogStack-SemEHR/RESTful_service
ExecStart=/opt/semehr/venv/bin/python3 webserver.py -p 8080
TimeoutStopSec=1
Restart=always
RestartSec=2
StartLimitInterval=0
User=semehr
Group=semehr

[Install]
WantedBy=multi-user.target
```

* Enable: `systemctl enable semehr.service`
* Logs:  `journalctl -u semehr.service  --since=today`
* Status: `systemctl -l --no-pager status semehr.service`
See http://www.freedesktop.org/software/systemd/man/systemd.service.html

Install CogStack-SemEHR into /opt, create the `semehr` user, create virtual environment:
```
sudo groupadd -g 8485
sudo useradd -g semehr -s /bin/false -u 8485 semehr
sudo mkdir /opt/semehr
sudo chown semehr:semehr /opt/semehr
sudo -u semehr virtualenv /opt/semehr/venv
sudo -u semehr bash -c "(source proxy_env; source /opt/semehr/venv/bin/activate; pip install -r structuredreports/src/tools/requirements.txt)"
sudo rsync -a CogStack-SemEHR /opt/semehr/
sudo ln -s ../utils.py /opt/semehr/CogStack-SemEHR/RESTful_service/utils.py
sudo chown -R semehr:semehr /opt/semehr/CogStack-SemEHR
```

To deploy inside docker please see [Dockerfile.md](../Dockerfile.md)

## HTML structure

The main search page is vis.html.  This is a standalone client-side search interface.
There is no state maintained in the web server, it is all held in the client.

vis.html has external requirements: `jquery.min.js`, `jquery.dataTables.js`, `jquery.dataTables.css` and three images.

The API URL is hard-coded in `api.js` (`service_url: "http://localhost:8000/api"`).

## JavaScript structure

vis.js makes these calls to the API:
```
qbb.inf.needPassphrase( -- calls /api/need_passphrase
qbb.inf.checkPhrase(phrase  -- calls /api/check_phrase
qbb.inf.getMappings( -- calls /api/mappings
qbb.inf.getDocList( -- calls /api/docs
qbb.inf.getDocDetail(_curDoc -- calls /api/doc_detail
qbb.inf.getDocDetailMapping(_curDoc, _curMapping  -- calls /api/doc_content_mapping
qbb.inf.searchDocs($('#klsearch').val()  -- calls /api/search_docs
qbb.inf.searchAnnsMapping($('#klsearch').val(), _curMapping  -- calls /api/search_anns_by_mapping
qbb.inf.searchAnns($('#klsearch').val()  -- calls /api/search_anns
```

## Query API

A list of API calls (note that if a trailing slash is shown below then it is mandatory):

```
/api/docs - return a list of documents (not useful)
/api/need_passphrase/ - returns true or false to indicate whether a passphrase is needed for all API calls
/api/check_phrase/PHRASE/ - returns true or false, checks if the password is correct
/api/doc_detail/DOCID/ - returns the annotations on the document
/api/doc_content_mapping/DOCID/MAPPING/
/api/search_docs/QUERY/ - search within documents
/api/search_anns/QUERY/ - search within annotations
/api/search_anns_by_mapping/QUERY/MAPPING/
/api/mappings/ - return list of mapping names, eg. ["mapping 1", "mapping 2"]
```

If a password is needed (`need_passphrase` returns `true`) then you can check a given
password using `check_phrase` which should return `true` if correct. After that all
API calls must have a password in the query string, for example `?passphrase=PHRASE`.
Note that `PHRASE` is the sha256-encoded version of the password. You can test this
on the command line with `printf "passphrase" | sha256sum`.

The query string can have a `callback=` parameter if called from jQuery.
This is used by the `/vis/` web application.
Return values will be wrapped with the callback function name.

The most common use of the API is to make a database query with `/api/search_anns`
followed by retrieving the annotations and content of a document with `/api/getDocDetail`.

The API has been extended for use within SMI by adding additional query terms.
Alongside the query terms are filtering terms which reduce the scope of the search
to specific modalities or a range of dates.

The query is encoded as a JSON object string, not a traditional HTML form.

The reason for doing it this way is because it has to be submitted as a GET query
string not a POST due to CORS. Also GET has a low limit on length. The JSON format
allows a much more flexible set of query terms.

Most items are optional. Optional fields should not be transmitted, so that the
server can determine a sensible default value.
```
/api/search_anns/term/?j=JSON - where JSON is a structure like this:

"terms" = [
  { "q" = "QUERY", (free text or comma-separated list of CUIs or SNOMED codes, possibly preceded by - to negate?)
    "qdepth" = N, (limit the query expansion to depth N)
    "qstop" = [ "Cnnnnn", ], (remove CUIs from the expanded list)
    "negation = "Any" or "Negated" or "Affirmed",
    "experiencer" = "Patient" or "Other",
    "temporality" = ["Recent" or "historical" or "hypothetical"]
  },
],
"filter" = {
  "start_date" = "YYYY-MM-DD",
  "end_date" = "YYYY-MM-DD",
  "modalities" = [ "CT", "MR", "US", "PT", "CR", "OT", "XA", "RF", "DX", "MG", "PR", "NM" ]
},
"returnFields" = [ "SOPInstanceUID", "SeriesInstanceUID", "StudyInstanceUID" ]
```

Note that the JSON structure will obviously have to be a single line of text encoded
suitably for a GET URL.

Alternatively the query can be submitted using POST if it is large.
The content needs to be a dictionary containing "terms" at the top level
along with optional "passphrase", "filter" and "returnFields".
The passphrase has to be in here and not in the URL.

All fields except "terms[q]" are optional (omit them rather than trying to provide a
default value, so that the API itself can choose a suitable default value).

The returnFields typically is only used for returning the SOPInstanceUID but if more
than one field is requested then each row in the results will have an array of the
values in the same order as requested. (To be confirmed: the result could be a dict
instead to prevent confusion).

The CUI to search for is typically something like Cnnnnnnn where n is a digit,
eg. C0205076 (which is "Chest Wall"), but can also be a SNOMED code
which is a string of only digits. The given code will be expanded in the dictionary
to include all sub-codes. If given free-text then it will currently only be matched
against the 'pref' field in the database using a full-string case-sensitive match
(to be confirmed).

Note that the date format in the query is "YYYY-MM-DD" but the date stored in the database
is in DICOM format which is YYYYMMDD. If any dates are returned they will be in DICOM format.

The response is a dictionary of the form:
```
{
  "success": true,
  "num_results": 2,
  "results": [ ... ]
}
```

Each element of results will be a single string value, when the query requests a single element,
for example, if requesting SOPInstanceUID,
`"results": [ "1.2.3", "3.4.5", ... ]`
or will be a dictionary when the query requests multiple elements,
for example, if requesting SOPInstanceUID,SeriesInstanceUID, 
`"results": [ { "SOPInstanceUID": "1.2.3", "SeriesInstanceUID": "3.4.5" }, ... ]`

If an error occurs the response is:
```
{
  "success": false,
  "message": "..."
}
```
