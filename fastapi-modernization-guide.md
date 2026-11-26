# FastAPI Service Modernization Guide

A step-by-step migration guide distilled from the refactor of **fastpostal**
(FastAPI + uv + uvicorn + pydantic v2 + slowapi, deployed via systemd).

The refactor ran as six small phases. Each one leaves the service fully working —
tests green, server boots, endpoints behave identically — before the next starts.
Commit after each phase; a broken intermediate state is one `git reset` away.

Parts marked *(if applicable)* only apply if your service has the matching
component (rate limiting, systemd, SSL, ...).

## Guiding principles

1. **One task at a time.** Never mix "restructure" with "change behavior".
2. **Preserve behavior first, improve second.** Phases 1–3 keep env var names,
   defaults, and response shapes byte-identical. Only phase 4 changes behavior,
   deliberately and testably.
3. **Verify after every phase** — the loop below is not optional.
4. **Docs live with the code.** AGENTS.md / README / sample.env are updated in the
   *same* commit as the code they describe. They double as your behavioral spec.
5. **`git mv` for every rename** — history pays off later. Untracked files need a
   plain `rm` (git won't track their deletion).

## The verification loop (after every phase)

```bash
uv sync              # after ANY pyproject.toml change (installs console scripts!)
uv run pytest
uv run ruff check .
ty check .           # if ty is installed
```

Plus a live smoke test (adjust host/port):

```bash
# Boot via the real entrypoint and the real .env
setsid uv run serve >/tmp/smoke.log 2>&1 & PID=$!; sleep 6

# Every route, including auth failure and success
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/parse?address=x   # 401
curl -s -H "X-API-KEY: k" "http://127.0.0.1:8080/parse?address=x"               # 200
curl -s http://127.0.0.1:8080/health                                            # 200
kill -- -$PID; sleep 1

# Negative test: a misconfiguration must refuse to start
env ENVIRONMENT=PROD ACCESS_KEY= uv run serve    # expect: exit 1, one-line error
```

Also verify *(if you touched logging)*: emit a line from a `pkg.*` logger and grep
both stderr and the log file — a dictConfig change that silently drops app logs is
the easiest way to lose production tracebacks.

---

## Phase 0 — Baseline & documentation

Goal: a trusted behavioral spec before anything moves.

- Read every file. Enumerate **all env vars and their defaults** — this list is the
  contract phases 1–3 must not break.
- Write `AGENTS.md`: commands, how it's wired (imports, entrypoints, deploy), how
  tests work. Future-you (and future agents) rely on it.
- Reconcile `README.md` and `sample.env` against reality; delete dead env vars.
- Get `pytest` + `ruff` green *before* touching anything. Fix or explicitly skip
  known-broken tests.

**Done when:** docs describe the *current* code accurately; test suite green.

---

## Phase 1 — Centralize configuration

Goal: one source of truth for config; no module reading env vars ad hoc or importing
config values from another module (the classic `main.py` ↔ `app.py` cycle).

- `uv add pydantic-settings`
- New `pkg/config.py`:

```python
from __future__ import annotations   # <-- important, see Gotcha #3

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEV = "DEV"
    DEBUG = "DEBUG"
    PROD = "PROD"


class Settings(BaseSettings):
    """Runtime configuration; real env vars take precedence over .env values."""

    model_config = SettingsConfigDict(env_file=".env")

    environment: Environment = Environment.PROD
    host: str = "127.0.0.1"
    port: int = 8080
    access_key: str = ""
    log_path: Path = Path("./logs")

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def access_keys(self) -> list[str]:
        """Split the comma-separated ACCESS_KEY env var into a list."""
        return [k.strip() for k in self.access_key.split(",") if k.strip()]

    @property
    def log_level(self) -> str:
        return "debug" if self.environment == Environment.DEBUG else "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

  Patterns to copy:
  - **Enum + `mode="before"` validator** for case-insensitive env values.
  - **CSV env var → property** (`access_keys`), not a parser in the route.
  - **Derived values as properties** (`log_level`, `workers`) — they're not env vars.
  - **`lru_cache`d `get_settings()`** — cheap per-request config access.
- Slim `main.py` down to a launcher: `settings = get_settings()` → `uvicorn.run(...)`.
  `app.py` reads config via `get_settings()`; the two modules no longer import each other.
- Drop direct `load_dotenv()` calls — pydantic-settings reads `.env`, and real env
  vars still win (same precedence as dotenv).

**Do not** rename env vars or change defaults in this phase.

**Done when:** launcher + app both source config from `Settings`; suite green.

---

## Phase 2 — App factory

Goal: testability without env-var manipulation or `sys.modules` surgery.

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app for the given settings (process defaults when omitted)."""
    settings = settings or get_settings()
    limiter = Limiter(key_func=get_remote_address)   # per-app state!
    app = FastAPI()
    app.state.limiter = limiter
    # ... middleware, routes ...
    return app


# Module-level instance so `uvicorn pkg.app:app` keeps working.
app = create_app()
```

Key points:

- **Create the limiter (and any other per-process state) inside the factory.**
  A module-level limiter is shared across every app instance and poisons test
  isolation (rate-limit buckets leak between tests).
- The module-level `app = create_app()` is a bridge so the uvicorn import string
  (`uvicorn pkg.app:app`) and the systemd unit keep working unchanged.

Rewrite test fixtures to be hermetic:

```python
@pytest.fixture()
def client_prod() -> TestClient:
    return TestClient(create_app(Settings(environment="PROD", access_key="test-key-123")))

@pytest.fixture()
def client_dev() -> TestClient:
    return TestClient(create_app(Settings(environment="DEV")))
```

Delete: `os.environ[...] = ...` in tests, `sys.modules` purging, any
`_get_app(mode)` helper. Tests no longer depend on the repo's `.env` or import order.

Config tests must opt out of `.env` entirely: `Settings(_env_file=None, **kwargs)`.

**Done when:** zero env-var writes or module purges in tests; suite green.

---

## Phase 3 — Proper package layout

Goal: stop shipping a package literally named `src` and a dual `src/` + `config/`
top-level split where `config/` mixes Python with ops artifacts.

```
main.py                      # temporary shim only — delete after deploy update
src/pkg/
├── __init__.py
├── app.py                   # create_app(...)
├── config.py                # Settings / get_settings
├── models.py                # pydantic request/response models
├── parse_service.py         # (phase 5)
├── logging_config.py        # build_log_config(...)
└── serve.py                 # serve() → uvicorn.run("pkg.app:app", ...)
config/
└── pkg.service              # ops artifacts only — no Python
```

Steps:

1. `git mv` each file (rename history preserved). Python that lived in ops dirs
   (`config/logging.py`) moves into the package; the ops dir keeps only deploy
   artifacts.
2. Build backend:
   - `uv_build`: `module-name = "pkg"`, `module-root = "src"`
   - setuptools: `[tool.setuptools.packages.find] where = ["src"]`
   - hatch: `[tool.hatch.build.targets.wheel] packages = ["src/pkg"]`
3. One console script, named for what it does:

   ```toml
   [project.scripts]
   serve = "pkg.serve:serve"
   ```

   If you have two entrypoints, pick one. "The right" name is the verb:
   `serve` beats the package name.
4. **Deploy first, delete the shim second.** Update the systemd unit
   (`ExecStart=uv run serve`), copy it to the host, `systemctl daemon-reload &&
   systemctl restart pkg`. Only then remove the root shim.
5. `uv sync` (installs the script; verify `.venv/bin/serve` exists) and smoke-test
   **every** launch path that must keep working.

**Done when:** `import pkg.app` works, both old and new launch paths boot, docs synced.

---

## Phase 4 — Correctness

The **only** phase allowed to change behavior. Work through the checklist; each item
is independent and individually testable.

- [ ] **Blocking work in `async def` handlers → make them `def`.** uvicorn runs
      sync handlers in a thread pool; an `async def` doing a native/IO-blocking call
      stalls the *entire* event loop of that worker. (fastpostal's `/health` parsed
      an address via libpostal inside `async def` — fixed with one keyword.)
- [ ] **Fail-fast config validation** in a `model_validator(mode="after")`:

  ```python
  @model_validator(mode="after")
  def _fail_fast(self) -> Settings:
      if self.environment in (Environment.DEBUG, Environment.PROD) and not self.access_keys:
          raise ValueError("ACCESS_KEY must be set when ENVIRONMENT is DEBUG or PROD")
      # ... paired settings must be set together; file paths must exist ...
      return self
  ```

  Misconfiguration that only surfaces mid-request (e.g. auth required but no keys
  configured → every request 401 forever) becomes a startup error.
- [ ] **Clean startup failure**: catch `ValidationError` in `serve()` and
      `raise SystemExit(f"Configuration error:\n{exc}")` — one-line error, exit 1,
      not a pydantic traceback under systemd.
- [ ] **No exception text in client responses.** `logger.exception(...)` server-side,
      generic message in the 500 body. Internal paths/stacks in HTTP responses are a
      leak, not a convenience.
- [ ] **Rate limit state** *(if slowapi)*: the in-memory limiter is **per worker
      process** — with N workers the real cap is N × limit. Document it; a strict
      global cap needs a shared backend (Redis). Don't silently "fix" it.
- [ ] **`forwarded_allow_ips`** *(if reverse-proxied)*: never `"*"`. Any client who
      can set `X-Forwarded-For` can rewrite their client IP — including resetting
      their per-IP rate-limit bucket. Default to local proxies only
      (`127.0.0.1,::1`), make it configurable, keep the list short.
- [ ] Audit the rest: missing `response_model`s, `/docs` and `/openapi.json`
      publicly exposed in prod (gate with your auth or disable), N+1 queries,
      etc.

**Done when:** each checked item has a test (e.g. `test_config.py` for fail-fast) and
the live smoke test's negative case shows the server refusing to boot.

---

## Phase 5 — Polish

- **Extract a service module** for any third-party engine the app calls
  (`parse_service.py`, `mail_service.py`, ...). It is the *only* module that imports
  the engine, and it exposes small functions returning typed models:

  ```python
  """Parsing service: the single place that calls libpostal."""
  from postal import parser          # NOTE: module import, see Gotcha #1
  from .models import ParsedComponent

  def parse(address: str) -> list[ParsedComponent]:
      return [ParsedComponent(label=l, value=v) for v, l in parser.parse_address(address)]
  ```

  **Critical — import the module, not the function.** `parser.parse_address(x)`
  resolves the attribute at *call* time, so existing tests that do
  `patch("postal.parser.parse_address")` keep working. A `from postal.parser import
  parse_address` at module top would bind the original function and silently defeat
  every mock. Leave a comment saying why, or a future "cleanup" will break tests.
- **`__name__` loggers.** Replace `logging.getLogger("uvicorn.default")` grabs with
  `logging.getLogger(__name__)`. Then add a package entry to the dictConfig with
  **the same handlers the old logger had** — behavior preservation, not a logging
  redesign:

  ```python
  "fastpostal": {"handlers": ["default", "file"], "level": "INFO", "propagate": False}
  ```

  Missing this entry means your app logs silently fall through to the root logger
  (stderr only, no file) — you lose file tracebacks without any test failing.
- **Make the log config a pure build function** fed from settings:
  `build_log_config(log_path, level)` — no `os.environ` reads, no `load_dotenv()`,
  no dir creation at *import* time. The settings object is the only input.
- **Dependency hygiene:** anything that's now only transitive gets `uv remove`d
  (e.g. `python-dotenv` once pydantic-settings reads `.env` itself). Check
  `uv.lock` that it survives transitively if it must.

**Done when:** routes are thin (try/except + HTTP semantics only), all modules type-
and lint-clean, docs describe the new layering.

---

## Phase 6 — Static analysis

Run `ty check .` (Ruff's checker; pyright/mypy work too). In fastpostal it found 3
real issues the runtime never surfaced:

1. **slowapi's private handler vs Starlette's signature** —
   `_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response`
   isn't a valid `ExceptionHandler` (must accept `Exception`). Fixed with an adapter:

   ```python
   def rate_limit_handler(request: Request, exc: Exception) -> Response:
       # Registered for RateLimitExceeded only, so this always holds at runtime.
       return _rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))
   ```

2. **`Model(**d)` where `d: dict[str, str | None]`** and some fields are
   non-optional — rejected by the checker. Fixed properly: the service returns typed
   models instead of loose dicts.

Recommendation: add the checker as a dev dependency (`uv add --dev ty`) so it runs
inside the project environment, and make it a pre-commit habit.

---

## Testing patterns (reference)

- **Hermetic fixtures** — build `Settings(...)` directly; no env vars, no
  `sys.modules`, no repo `.env` influence.
- **Mock at the source module** (`patch("postal.parser.parse_address")`), and keep
  the code under test calling through the module so the patch sticks.
- **Per-app state in tests** — because the factory builds the limiter per app, each
  `TestClient` gets its own rate-limit buckets; a shared module-level limiter leaks
  state between tests.
- **Config validation tests** with `Settings(_env_file=None, ...)` — cover each
  fail-fast rule, the happy paths, and case-insensitivity.
- **Live tests the suite can't see:** 429 path (61 rapid requests), fail-fast boot
  refusal, log routing (apply `build_log_config` via `dictConfig`, emit from a
  `pkg.*` logger, grep stderr + log file).

## Deployment notes (systemd + uv)

- `ExecStart=uv run serve` — keep the console script as the single entrypoint.
- After changing the unit file on the host: `systemctl daemon-reload &&
  systemctl restart pkg`.
- Watch the unit's `WorkingDirectory` — a stale path (pointing at an old checkout)
  means the deployed service silently runs *old code*.

## Gotchas (the ones that actually bit)

1. **`from a.b import f` vs `import a.b`.** Binding a function at import time defeats
   `patch("a.b.f")`. For mocked third-party calls, call through the module.
2. **`dictConfig` level names are case-sensitive.** `"level": "info"` →
   `ValueError: Unknown level: 'info'`. Use `"INFO"` (unlike `Logger.setLevel`,
   which is case-insensitive).
3. **Self-annotation inside a class body.** `def _fail_fast(self) -> Settings:`
   fails with `NameError` — the class doesn't exist yet. `from __future__ import
   annotations` defers evaluation and fixes it.
4. **uvicorn's `log_level` kwarg overrides the dictConfig** for `uvicorn.*` loggers
   after the config is applied — don't chase "why is uvicorn.error at DEBUG when my
   dict says INFO".
5. **`lru_cache`d `get_settings()` + tests.** Purging `sys.modules` resets the cache,
   but it's a footgun; constructing `Settings(...)` directly (phase 2) removes the
   need entirely.
6. **In-memory rate limiting × N workers** = N × the limit. Real, and usually
   acceptable — just document the true number.
7. **`X-Forwarded-For` spoofing** resets per-IP rate-limit buckets if the client IP
   is trusted from `forwarded_allow_ips="*"`.
8. **`git mv` vs `rm`.** Tracked renames need `git mv` (history); untracked files
   need plain `rm` (`git rm` fails with "pathspec did not match").
9. **`uv sync` after `[project.scripts]` changes** — the console script only appears
   in `.venv/bin` after the env is rebuilt.
10. **Blocking call inside `async def`** freezes every concurrent request on that
    worker, not just the one that called it.
11. **Log-config edits with no visible test.** The dictConfig change that drops app
    logs from the file handler passes every test — verify routing live.
12. **Env var names/defaults are a public contract** until phase 4. Renaming or
    re-defaulting them mid-refactor changes behavior for anyone running the old env.

## Definition of done (whole refactor)

- [ ] `pytest` / `ruff` / `ty` all green
- [ ] Live smoke test: boot, every route (200/401/503/429), fail-fast refusal, log routing
- [ ] AGENTS.md, README, sample.env describe the *new* structure with zero stale references
      (grep for the old module paths and function names — comments rot too)
- [ ] One entrypoint; deploy artifacts reference it; host unit file updated
- [ ] One commit per phase, each independently green
