#!/bin/bash
set -e
cd "$(dirname "$0")"

mv GeoLite2-City.mmdb GeoLite2-City.mmdb.old 2>/dev/null || true
wget https://cdn.jsdelivr.net/npm/geolite2-city/GeoLite2-City.mmdb.gz
gzip -d GeoLite2-City.mmdb.gz
