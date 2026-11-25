# AGENTS.md

FastAPI geo-IP lookup service (FastAPI + uvicorn + geoip2, Python 3.12, managed with `uv`).

## Run

- Copy `sample.env` to `.env` and set at least `ACCESS_KEY` (comma-separated list of accepted `X-API-KEY` values) — required in practice for `PROD`/`DEBUG` (see "Behavior gotchas"). `*.mmdb` and `.env` are gitignored.
- Requires `db/GeoLite2-City.mmdb` (not in git). Refresh it with `bash db/update.sh` (downloads from jsdelivr, keeps a `.old` backup of the previous database).
- Start: `uv run main.py` — must run from the repo root: the database path (`./db/GeoLite2-City.mmdb`) and `LOG_PATH` are CWD-relative. `main.py` is a thin launcher: `get_settings()` → `uvicorn.run("src.app:app", ...)`. `src/app.py` reads its config via `get_settings()` — `main` and `app` no longer import each other.
- `ENVIRONMENT` env var: `DEV` → `--reload`, 1 worker, **auth bypassed** (for easy local testing); `DEBUG` → debug log level; `PROD` (default) → `(cpu_count*2)+1` workers.
- Optional `SSL_CERT`/`SSL_KEY` (file paths, used together) enable HTTPS in uvicorn.

## Config (env vars)

All env vars flow through `src/config.py` (`Settings`, pydantic-settings): the cached `get_settings()` reads `.env` and real environment variables (the latter win — same precedence as dotenv). `main.py` creates `LOG_PATH` before starting uvicorn; `config/logging.py` is a pure `build_log_config(log_path)` with no env access or import-time side effects.

| Var | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `PROD` | `DEV`, `DEBUG` or `PROD` (case-insensitive) |
| `HOST` | `127.0.0.1` | bind address |
| `PORT` | `8080` | bind port |
| `SSL_CERT` | unset | HTTPS certificate path |
| `SSL_KEY` | unset | HTTPS key path |
| `ACCESS_KEY` | empty | comma-separated accepted `X-API-KEY` values |
| `LOG_PATH` | `./logs` | directory for the rotating `access.log` |
| `DB_PATH` | `./db/GeoLite2-City.mmdb` | GeoLite2-City database location (new optional override; default = previous hardcoded path) |

`workers` (PROD: `cpu_count*2+1`, otherwise 1) and `log_level` (DEBUG → `debug`, else `info`) are derived in `Settings` properties, not env vars.

## Behavior gotchas

- Every endpoint requires the `X-API-KEY` header to be in `ACCESS_KEYS` (failures return 403 and are **not** logged) except paths in `NO_AUTH_PATHS` (currently `/geoip/health`). In `ENVIRONMENT=DEV` the auth middleware is bypassed entirely.
- In `PROD` with an empty `ACCESS_KEY` every request is a 403 — there is no startup validation, the misconfiguration only shows up mid-request.
- OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are currently **enabled** (FastAPI defaults; a previous fix that disabled them was reverted).
- slowapi rate limits: `/geoip/` 5/min, `/geoip/geolookup` 60/min, `/geoip/health` 5/min — in-memory, per worker process (with N workers the effective cap is N × limit).
- Client IP: uvicorn runs with `proxy_headers=True, forwarded_allow_ips="*"`, which rewrites `request.client` from `X-Forwarded-For` for any peer. `get_ip_header`'s header fallbacks (`X_REAL_IP`, `HTTP_X_FORWARDED_FOR`) only trigger if `request.client.host` is invalid; in non-`PROD` mode it returns the `Host` header instead.
- IP validation problems (bad format, loopback, private) return **HTTP 200** with a `{"detail": "..."}` body — that is the existing API contract (tests assert it).
- `lookup_ip_address` opens a fresh `geoip2.database.Reader` per request.
- `subdivisions.most_specific.name` / `city.name` are accessed unguarded: a database entry without a subdivision or city yields an unhandled 500.
- Access + error logs go to `LOG_PATH/access.log` (rotating, 1 MB × 5) via `config/logging.py`; application loggers grab the `uvicorn.default` logger (no `src` package entry in the dictConfig — app logs reach the file only by propagation through `uvicorn`).

## Verification

- Tests: `uv run pytest` — 23 tests. The `client_prod`/`client_dev` fixtures purge `sys.modules` and rewrite `os.environ` before importing `src.app`, so tests are not hermetic (they depend on import order and the repo's `.env`).
- Lint: `uv run ruff check .` (rules `E`, `F`; `F401` ignored).
- No typechecker is configured or run.

## Toolchain & deployment

- `pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"` — dependency resolution only considers packages ≤ 7 days old.
- The project builds as package `src` (uv_build, `module-name = "src"`, `module-root = ""`). There is no console script; the only entrypoint is `uv run main.py`.
- Deployed as a systemd service (`config/fastgeoip.service`, `ExecStart=uv run main.py`). Dev environment is Windows; production is Linux.
