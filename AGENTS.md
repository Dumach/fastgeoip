# AGENTS.md

FastAPI geo-IP lookup service (FastAPI + uvicorn + geoip2, Python 3.12, managed with `uv`).

## Run

- Copy `sample.env` to `.env` and set at least `ACCESS_KEY` (comma-separated list of accepted `X-API-KEY` values) — required in `PROD`/`DEBUG`: the server refuses to start without it (see "Behavior gotchas"). `*.mmdb` and `.env` are gitignored.
- Requires `db/GeoLite2-City.mmdb` (not in git). Refresh it with `bash db/update.sh` (downloads from jsdelivr, keeps a `.old` backup of the previous database).
- Start: `uv run serve` (console script → `fastgeoip.serve:serve`) — must run from the repo root: the database path (`./db/GeoLite2-City.mmdb`) and `LOG_PATH` are CWD-relative. The launcher is thin: `get_settings()` → fail-fast checks → `uvicorn.run("fastgeoip.asgi:app", ...)`. The app is built by `create_app(settings)` in `src/fastgeoip/app.py`; `src/fastgeoip/asgi.py` owns the module-level `app` so `import fastgeoip.app` stays side-effect free and uvicorn's `--reload` worker still has an import string to follow.
- `ENVIRONMENT` env var: `DEV` → `--reload`, **auth bypassed** (for easy local testing); `DEBUG` → debug log level; `PROD` (default). All modes run a single worker (see `Settings.workers`).
- `uv run serve` **fails fast** (exit 1, one-shot readable message on stderr, no traceback) when: `ACCESS_KEY` is empty in `PROD`/`DEBUG`, `SSL_CERT`/`SSL_KEY` are set asymmetrically or point to missing files, or the `DB_PATH` file is missing.
- Optional `SSL_CERT`/`SSL_KEY` (file paths, used together, both must exist) enable HTTPS in uvicorn.

## Config (env vars)

All env vars flow through `src/fastgeoip/config.py` (`Settings`, pydantic-settings): the cached `get_settings()` reads `.env` and real environment variables (the latter win — same precedence as dotenv). `python-dotenv` is no longer a direct dependency; it remains installed transitively via pydantic-settings. `src/fastgeoip/logging_config.py` is a pure `build_log_config(log_path, level)` with no env access or import-time side effects.

| Var | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `PROD` | `DEV`, `DEBUG` or `PROD` (case-insensitive) |
| `HOST` | `127.0.0.1` | bind address |
| `PORT` | `8080` | bind port |
| `SSL_CERT` | unset | HTTPS certificate path (must exist when set) |
| `SSL_KEY` | unset | HTTPS key path (must exist when set) |
| `ACCESS_KEY` | empty | comma-separated accepted `X-API-KEY` values (required in `PROD`/`DEBUG`) |
| `LOG_PATH` | `./logs` | directory for the rotating `access.log` |
| `DB_PATH` | `./db/GeoLite2-City.mmdb` | GeoLite2-City database location (must exist at startup) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` | peers uvicorn trusts for `X-Forwarded-For` (tightened from the old `"*"`) |

`workers` (always 1 — PROD scaling was removed for memory reasons) and `log_level` (DEBUG → `debug`, else `info`) are derived in `Settings` properties, not env vars. `Settings` has a fail-fast `model_validator`: empty `ACCESS_KEY` in `PROD`/`DEBUG`, asymmetric `SSL_CERT`/`SSL_KEY`, and missing SSL files raise `ValidationError`.

## Behavior gotchas

- Routes: `GET /` (client IP), `GET /geolookup?ip=<ip>`, `GET /health` (no `/geoip` prefix).
- Every endpoint requires the `X-API-KEY` header to be in `ACCESS_KEYS` (failures return 403 and **log a warning** with method/path/client) except paths in `NO_AUTH_PATHS` (currently `/health`). In `ENVIRONMENT=DEV` the auth middleware is bypassed entirely. The middleware is registered as `@app.middleware("http")`.
- Misconfiguration fails fast at startup (see Run section) — a `PROD` server can no longer silently 403 every request.
- OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are **disabled** (`docs_url`/`redoc_url`/`openapi_url=None`); even with a valid key they 404. The API is documented in the README.
- slowapi rate limits: `/` 5/min, `/geolookup` 60/min, `/health` 5/min — in-memory, per worker process (with N workers the effective cap is N × limit; currently always 1 worker).
- Client IP: uvicorn runs with `proxy_headers=True, forwarded_allow_ips` = `FORWARDED_ALLOW_IPS` (default `127.0.0.1,::1`), which rewrites `request.client` from `X-Forwarded-For` only for those peers. `get_ip_header`'s header fallbacks (`X_REAL_IP`, `HTTP_X_FORWARDED_FOR`) only trigger if `request.client.host` is invalid; in non-`PROD` mode it returns the `Host` header instead.
- IP validation problems (bad format, loopback, private) return **HTTP 200** with a `{"detail": "..."}` body — that is the existing API contract (tests assert it).
- `src/fastgeoip/geoip_service.py` is the only module importing `geoip2`. It imports the module (`import geoip2.database`), not the `Reader` class, so `patch("fastgeoip.geoip_service.geoip2.database.Reader")` resolves at call time. `get_reader` is `lru_cache`d per database path (one open reader per process); tests clear that cache via the shared fixture.
- GeoLite2 entries without country/subdivision/city yield **null** fields (guarded access), not a 500.
- Any other unhandled exception returns a generic `{"detail": "Internal server error"}` 500 and is logged server-side with a stack trace (`logger.exception`) — the real error never reaches the client.
- Access + error logs go to `LOG_PATH/access.log` (rotating, 1 MB × 5) via `src/fastgeoip/logging_config.py`; app loggers use `logging.getLogger(__name__)`, and the dictConfig has a `fastgeoip` entry with the same handlers as the old `uvicorn.default` logger (`default` + `file`, `propagate: False`). Without that entry app warnings/tracebacks would reach stderr but never the log file.

## Verification

- Tests: `uv run pytest` — 27 hermetic tests focused on core logic: `tests/test_config.py` (fail-fast validation), `tests/test_endpoints.py` (health, route happy paths, IP validation responses, null GeoIP fields), `tests/test_geoip_service.py` (lookups, reader caching) and `tests/test_ip_utils.py` (IP parsers). Shared fixtures live in `tests/conftest.py`: settings are built with `_env_file=None`, and `mock_geoip_reader` patches `fastgeoip.geoip_service.geoip2.database.Reader` while clearing `get_reader`'s cache. No `os.environ` writes, no `sys.modules` purging, no dependency on the repo's `.env`, and no tests for rate limits/auth/docs. `httpx2` must stay in the dev deps: `starlette.testclient` imports it at runtime but does not declare it upstream.
- Lint: `uv run ruff check .` (rules `E`, `F`; `F401` ignored).
- Typecheck: `uv run ty check .` (ty is a dev dependency). It currently reports a known baseline error: slowapi's `_rate_limit_exceeded_handler` is not a valid exception-handler signature (`src/fastgeoip/app.py`) — to be fixed deliberately in phase 6, not suppressed.

## Toolchain & deployment

- `pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"` — dependency resolution only considers packages ≤ 7 days old.
- The project builds as package `fastgeoip` (uv_build, `module-name = "fastgeoip"`, `module-root = "src"`), and installs the `serve` console script (`fastgeoip.serve:serve`) — in the venv that is `.venv/bin/serve`.
- Dev dependencies: `python-dotenv` and `pytest-asyncio` were removed (transitive via pydantic-settings / no async tests); `httpx2` stays because `starlette.testclient` needs it.
- Deployed as a systemd service (`config/fastgeoip.service`, `ExecStart=/opt/fastgeoip/.venv/bin/serve`); `config/fix_permissions.sh` sets the ownership/permissions for that layout (root-owned, group `fastapi` readable, group-executable venv). Dev environment is Windows; production is Linux.
