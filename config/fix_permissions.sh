#!/bin/bash
# Prepare /opt/fastgeoip for the systemd unit (root-owned, group fastapi readable).
set -e
chown -R root:fastapi /opt/fastgeoip
chmod -R u=rwX,g=rX,o= /opt/fastgeoip
chmod g+x /opt/fastgeoip/.venv/bin/*
# Verify the service user can load the package (running `serve` directly would start the server)
sudo -u fastapi /opt/fastgeoip/.venv/bin/python -c "import fastgeoip.main"
