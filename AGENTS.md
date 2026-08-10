# AGENTS.md

FastAPI geo-IP lookup service (FastAPI + uvicorn + geoip2, Python 3.12, managed with `uv`).

## Run

- Copy `sample.env` to `.env` and set at least `ACCESS_KEY` (comma-separated list of accepted `X-API-KEY` values). `*.mmdb` and `.env` are gitignored.
- Requires `db/GeoLite2-City.mmdb` (not in git). Refresh it with `bash db/update.sh` (downloads from jsdelivr, keeps a `.old` backup).
- Start: `uv run main.py` — must run from repo root. `main.py` launches uvicorn with target string `"src.app:app"`; `src/app.py` imports top-level `main` and `config`, so paths break if invoked from elsewhere.
- `ENVIRONMENT` env var: `DEV` → `--reload`, 1 worker; `PROD` (default) → `(cpu_count*2)+1` workers; `DEBUG` → debug log level.
- Optional `SSL_CERT`/`SSL_KEY` enable HTTPS in uvicorn.

## Behavior gotchas

- Every endpoint requires `X-API-KEY` header in `ACCESS_KEYS` (failures return 403 and log the wrong key) except paths in `NO_AUTH_PATHS` (currently `/geoip/health`).
- slowapi rate limits: `/geoip/` 5/min, `/geoip/geolookup` 60/min, `/geoip/health` 5/min.
- OpenAPI/redoc are disabled (`docs_url=None`, `redoc_url=None`).
- Client IP: uvicorn runs with `proxy_headers=True, forwarded_allow_ips="*"`, which already rewrites `request.client` from X-Forwarded-For. Do NOT add manual XFF parsing in `get_ip_header`; its header fallbacks only trigger if `request.client.host` is invalid. In non-PROD mode it returns the `Host` header instead.
- Access + error logs go to `LOG_PATH/access.log` (rotating, 1 MB x 5) via `config/logging.py`.

## Verification

- Lint: `ruff check .` (rules `E`, `F`; `F401` ignored). No tests and no typecheck configured.

## Toolchain

- `pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"` — dependency resolution only considers packages ≤7 days old.
- Deployed as a systemd service (`config/fastgeoip.service`, `ExecStart=uv run main.py`, socket activation). Dev environment is Windows; production is Linux.
