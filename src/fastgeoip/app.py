"""FastAPI application factory: builds the app for a given Settings."""

from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from fastgeoip.config import Environment, Settings, get_settings
from fastgeoip.geoip_service import lookup_ip_address
from fastgeoip.ip_utils import get_ip_header, validate_ip
from fastgeoip.models import InternalServerErrorResponse, UnauthorizedResponse

logger: logging.Logger = logging.getLogger(__name__)

NO_AUTH_PATHS = {"/health"}


def rate_limit_handler(request: Request, exc: Exception) -> Response:
    """Adapter so slowapi's private handler matches Starlette's exception-handler signature."""
    # Registered for RateLimitExceeded only, so this always holds at runtime.
    return _rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app for the given settings (process defaults when omitted)."""
    settings = settings or get_settings()
    # In-memory state: the 60/minute limit applies per worker process, so with
    # N uvicorn workers the effective cap is 60 * N / min. A strict global
    # limit would need a shared backend (e.g. Redis).
    limiter = Limiter(key_func=get_remote_address)

    # OpenAPI docs are an info leak on a public service; the API is documented in the README.
    app = FastAPI(title="geoip", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """Require X-API-KEY header or token param on protected paths; skipped in DEV mode."""
        if request.url.path in NO_AUTH_PATHS:
            return await call_next(request)

        is_authenticated = False
        if request.headers.get("X-API-KEY") in settings.access_keys:
            is_authenticated = True
        if settings.environment == Environment.DEV:
            is_authenticated = True

        if is_authenticated:
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        logger.warning("Invalid API key for %s %s from %s", request.method, request.url.path, client_host)

        return JSONResponse(
            status_code=401,
            content=UnauthorizedResponse(
                error="unauthorized", detail="A valid API key is required to access this resource"
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        # Log the real error server-side; the client only gets a generic body.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=InternalServerErrorResponse(
                detail="Internal server error",
            ).model_dump(),
        )

    @app.get("/geolookup")
    @limiter.limit("10/minute")
    def get_geolookup(request: Request, ip: str) -> JSONResponse:
        ip = ip.strip()
        error = validate_ip(ip)
        if error != "":
            return JSONResponse({"detail": error})
        return JSONResponse(lookup_ip_address(ip, settings).model_dump())

    @app.get("/health")
    @limiter.limit("10/minute")
    def get_health(request: Request):
        ip = "1.1.1.1"
        try:
            result = lookup_ip_address(ip, settings)
        except Exception:
            logger.exception("Health check failed")
            return JSONResponse({"detail": "unhealthy"}, status_code=503)

        if not result.ip:
            return JSONResponse({"detail": "unhealthy"}, status_code=503)
        return JSONResponse({"detail": "healthy", "database": "ok"})

    # from app builder
    return app


# Module-level instance so `uvicorn fastgeoip.app:app` (fastgeoip.serve, systemd) keeps working.
app = create_app()
