# fastgeoip

FastAPI based geoIP lookup service. Results are based on the [GeoLite2-City](https://dev.maxmind.com/geoip/geolite2-free-geolocation-database/) dataset.

## Endpoints

| Method | Path | Auth | Rate limit | Description |
|---|---|---|---|---|
| `GET` | `/geoip/` | yes (DEV bypasses) | 5/min | Look up the client IP (from the connection, or `X-Forwarded-For` when proxied) |
| `GET` | `/geoip/geolookup?ip=<ip>` | yes (DEV bypasses) | 60/min | Look up the given IP address |
| `GET` | `/geoip/health` | no | 5/min | Health check: performs a real database lookup and reports `healthy` / `unhealthy` (503) |

Successful lookups return:

```json
{
  "country_code": "US",
  "country_name": "United States",
  "region_name": "California",
  "city": "San Francisco",
  "ip": "8.8.8.8"
}
```

Invalid, loopback or private input IPs return HTTP 200 with a `{"detail": "..."}` message (existing API contract).

## Authentication

Requests need an `X-API-KEY` header matching one of the comma-separated keys in `ACCESS_KEY`. Wrong or missing keys get a `403` (`/geoip/health` is exempt). With `ENVIRONMENT=DEV` the check is bypassed, for easy local testing.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (managed by uv via `.python-version`).

```bash
# 1. Install dependencies (creates .venv)
uv sync

# 2. Configure
cp sample.env .env
# edit .env — at minimum set ACCESS_KEY="your-key" for PROD/DEBUG

# 3. Download the GeoLite2-City database (kept in db/, refreshed by db/update.sh)
bash db/update.sh

# 4. Run (from the repo root — paths are CWD-relative)
uv run serve
```

The server listens on `HOST:PORT` (default `127.0.0.1:8080`). `SSL_CERT`/`SSL_KEY` enable HTTPS.

## Configuration

Configuration is read from environment variables and `.env` (real environment variables win).

| Var | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `PROD` | `DEV` (reload, 1 worker, no auth), `DEBUG` (debug logs) or `PROD` (`(cpu_count*2)+1` workers) |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8080` | Bind port |
| `SSL_CERT` | — | Path to the TLS certificate (used with `SSL_KEY`) |
| `SSL_KEY` | — | Path to the TLS private key |
| `ACCESS_KEY` | — | Comma-separated list of accepted `X-API-KEY` values |
| `LOG_PATH` | `./logs` | Directory for the rotating `access.log` (1 MB × 5) |

## Database

`db/GeoLite2-City.mmdb` is not in git. `db/update.sh` downloads the latest release from jsdelivr and keeps the previous file as `db/GeoLite2-City.mmdb.old`.

## Development

```bash
uv run pytest        # test suite
uv run ruff check .  # lint
uv run ty check .    # typecheck (one known baseline error, see AGENTS.md)
```

For development set `ENVIRONMENT=DEV`: uvicorn runs with `--reload`, a single worker and without auth checks.

## Production deployment (systemd)

The service is deployed as a systemd unit — see [`config/fastgeoip.service`](config/fastgeoip.service).

```bash
# Copy the unit to the host
sudo cp config/fastgeoip.service /etc/systemd/system/fastgeoip.service

# Reload systemd configuration
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable fastgeoip.service
sudo systemctl start fastgeoip.service

# Check status
sudo systemctl status fastgeoip.service

# View logs
sudo journalctl -u fastgeoip.service -f

# Graceful reload (zero downtime — HUP triggers a uvicorn worker reload)
sudo systemctl reload fastgeoip.service

# Restart (brief downtime)
sudo systemctl restart fastgeoip.service

# Stop the service
sudo systemctl stop fastgeoip.service
```

Watch the unit's `WorkingDirectory` — the database and log paths are relative to it; a stale path means the deployed service silently runs against the wrong files.

### Creating a self-signed certificate (optional)

```bash
openssl req -x509 -newkey rsa:4096 -subj '/CN=example.com/C=US' -new -sha256 -days 3650 -nodes -keyout key.pem -out cert.pem
```

Then set `SSL_CERT`/`SSL_KEY` in the service's environment.
