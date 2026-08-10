## Create self-signed cert
```bash
openssl req -x509 -newkey rsa:4096 -subj '/CN=aruljohn.com/C=US' -new -sha256 -days 3650 -nodes -keyout key.pem -out cert.pem
```

# Create socket directory
sudo mkdir -p /var/run/uvicorn
sudo chown www-data:www-data /var/run/uvicorn

# Reload systemd configuration
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable fastgeoip.socket
sudo systemctl enable fastgeoip.service
sudo systemctl start fastgeoip.socket
sudo systemctl start fastgeoip.service

# Check status
sudo systemctl status fastgeoip.service

# View logs
sudo journalctl -u fastgeoip.service -f

# Graceful reload (zero downtime)
sudo systemctl reload fastgeoip.service

# Restart (brief downtime)
sudo systemctl restart fastgeoip.service

# Stop the service
sudo systemctl stop fastgeoip.service