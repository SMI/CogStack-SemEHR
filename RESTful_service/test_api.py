#!/usr/bin/env python3
# Run some sample queries by calling the API and printing the JSON response

import ssl
ssl._create_default_https_context = ssl._create_unverified_context # disable certificate check for HTTPS
import urllib.request

port="8485" # azure VM or nsh-smi06
port="8000" # docker

passphrase="aa06b3414d1ef012810cff0cfa1e459318ebcdf033af6044bdde7533566b2c23"

url_prefix = f'https://localhost:{port}/api/search_anns/C0205076/?passphrase={passphrase}'
url_prefix = f'https://localhost:{port}/api/search_anns/x/?'

# Password?
url = f'https://localhost:{port}/api/need_passphrase/'
print('Need password? %s' % urllib.request.urlopen(urllib.request.Request(url)).read().decode())
url = f'http://localhost:{port}/api/check_phrase/{passphrase}/'
print('Check password? %s' % urllib.request.urlopen(urllib.request.Request(url)).read().decode())

passquery = f'&passphrase={passphrase}'

#url = url_prefix + '&' + 'j={"terms":[{"q":"C0205076","negation":"Any","experiencer":"Any","temporality":"Any"}],"filter":{"modalities":["MR","CT"],"start_date":"2020-02-02","end_date":"2021-09-07"},"returnFields":["SOPInstanceUID","StudyInstanceUID","ContentDate"]}'
#url = url_prefix + '&' + 'j={"terms":[{"q":"C0205076","negation":"Any","experiencer":"Any","temporality":"Any"}],"filter":{"modalities":["MR","CT"],"start_date":"2020-02-02","end_date":"2021-09-07"}}'

queries = [

    # I know this occurs in doc0001
    """{"terms":[{"q":"C0005824","negation":"Any","temporality":["Recent"]}],"filter":{"modalities":["CT"]}}""",

    # Test negation,temporality terms
    """{"terms":[{"q":"C0205076","negation":"Any","temporality":["Recent"]}],"filter":{"modalities":["CT"]}}""",

    # Test asking for SOPInstanceUID
    """{"terms":[{"q":"C0205076","negation":"Any","temporality":["Recent"]}],"filter":{"modalities":["CT"]},"returnFields":["SOPInstanceUID"]}""",

    # Test multiple modalities
    """{"terms":[{"q":"C0205076","negation":"Any","temporality":["Recent","historical"]}],"filter":{"modalities":["CT","MR"]},"returnFields":["StudyInstanceUID"]}""",

    # Test date range, and returning two fields
    """{"terms":[{"q":"C0205076","negation":"Any"}],"filter":{"start_date":"1989-01-01","end_date":"2022-01-01"},"returnFields":["SOPInstanceUID","SeriesInstanceUID"]}""",

    # Should return "success":false
    """""",

]

for query in queries:
    print('======================================================================================')
    query = query.replace('\n',' ').replace('\r','')
    url = url_prefix + '&j=' + query + passquery
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req).read().decode()
    print('--------------\n%s\n-------------\n' % resp)
