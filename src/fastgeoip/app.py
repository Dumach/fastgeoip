"""FastAPI application factory: builds the app for a given Settings."""

import logging
from ipaddress import ip_address

import geoip2.database
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from geoip2.models import City
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from fastgeoip.config import Environment, Settings, get_settings
from fastgeoip.models import IpLookupResponse

logger: logging.Logger = logging.getLogger("uvicorn.default")

NO_AUTH_PATHS = {"/health"}


def get_ip_header(request: Request, settings: Settings) -> str:
    ip = request.client.host if request.client else ""
    if not validIPAddress(ip):
        ip = request.headers.get("X_REAL_IP", "")
    elif not validIPAddress(ip):
        ip = request.headers.get("HTTP_X_FORWARDED_FOR", "")

    if settings.environment != Environment.PROD:
        ip = request.headers.get("Host") or ip
    return ip


def validIPAddress(IP: str) -> bool:
    try:
        type(ip_address(IP))
        return True
    except ValueError:
        return False


def validate_ip(IP: str) -> str:
    if not validIPAddress(IP):
        return "IPv4 or IPv6 address is in an incorrect format."
    ip_addr = ip_address(IP)
    if ip_addr.is_link_local or ip_addr.is_loopback:
        return "You are on localhost"
    if ip_addr.is_private:
        return "You are on a private network"
    return ""


def lookup_ip_address(IP: str, settings: Settings) -> IpLookupResponse:
    reader = geoip2.database.Reader(settings.db_path)
    response: City = reader.city(IP)
    return IpLookupResponse(
        country_code=response.country.iso_code,
        country_name=response.country.name,
        region_name=response.subdivisions.most_specific.name,
        city=response.city.name,
        ip=IP,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app for the given settings (process defaults when omitted)."""
    settings = settings or get_settings()

    app = FastAPI(title="geoip")
    # Per-app state: a shared module-level limiter would leak rate-limit
    # buckets across app instances (tests).
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("auth")
    async def auth_middleware(request: Request, call_next):
        if request.url.path in NO_AUTH_PATHS:
            return await call_next(request)

        is_authenticated = True
        if request.headers.get("X-API-KEY") not in settings.access_keys:
            is_authenticated = False
        if settings.environment == Environment.DEV:  # for easy testing
            is_authenticated = True

        if is_authenticated:
            return await call_next(request)
        return JSONResponse({"detail": "Invalid API key"}, status_code=403)

    @app.get("/")
    @limiter.limit("5/minute")
    def get_myip(request: Request) -> JSONResponse:
        ip = get_ip_header(request, settings).strip()

        error = validate_ip(ip)
        if error != "":
            return JSONResponse({"detail": error})
        return JSONResponse(lookup_ip_address(ip, settings).model_dump())

    @app.get("/geolookup")
    @limiter.limit("60/minute")
    def get_geolookup(request: Request, ip: str) -> JSONResponse:
        ip = ip.strip()
        error = validate_ip(ip)
        if error != "":
            return JSONResponse({"detail": error})
        return JSONResponse(lookup_ip_address(ip, settings).model_dump())

    @app.get("/health")
    @limiter.limit("5/minute")
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

    return app


# Module-level instance so `uvicorn fastgeoip.app:app` (fastgeoip.serve, systemd) keeps working.
app = create_app()
