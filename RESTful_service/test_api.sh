#!/bin/bash
baseurl="http://localhost:8000/api"

echo ========================================================= GET
curl --insecure \
     --get \
     --data-urlencode 'passphrase=aa06b3414d1ef012810cff0cfa1e459318ebcdf033af6044bdde7533566b2c23' \
     --data-urlencode 'j={"terms":[{"q":"C0205076"}],"filter":{"start_date":"2017-01-01","end_date":"2017-01-03"}}' \
     "${baseurl}"/search_anns/x/

echo ========================================================= POST FILE
curl --insecure \
     -d @hello \
     --data-urlencode 'passphrase=aa06b3414d1ef012810cff0cfa1e459318ebcdf033af6044bdde7533566b2c23' \
     "${baseurl}"/search_anns/x/
echo ========================================================= POST QUERY
curl --insecure \
     -X POST \
     -H "Content-Type: application/json" \
     -d '{"passphrase":"aa06b3414d1ef012810cff0cfa1e459318ebcdf033af6044bdde7533566b2c23","terms":[{"q":"C0205076"}],"returnFields":"SeriesInstanceUID"}' \
     "${baseurl}"/search_anns/x/

