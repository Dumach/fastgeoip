#!/bin/bash
chown -R root:fastapi /opt/fastgeoip
chmod -R u=rwX,g=rX,o= /opt/fastgeoip
chmod g+x /opt/fastgeoip/.venv/bin/*
sudo -u fastapi /opt/fastgeoip/.venv/bin/serve --help