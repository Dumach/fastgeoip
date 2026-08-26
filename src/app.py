from geoip2.models import City
from src.model import IpLookupResponse
from ipaddress import ip_address
import logging
import time

from anyio import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import geoip2.database

from main import ProductionMode, mode, ACCESS_KEYS

app = FastAPI(title="geoip")
logger: logging.Logger = logging.getLogger("uvicorn.default")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

DB_PATH: Path = Path(".") / "db" / "GeoLite2-City.mmdb"

NO_AUTH_PATHS = {"/geoip/health"}


@app.middleware("auth")
async def auth_middleware(request: Request, call_next):
    is_authenticated = True
    if request.headers.get("X-API-KEY") not in ACCESS_KEYS:
        is_authenticated = False
    if mode == ProductionMode.DEV:  # for easy testing
        is_authenticated = True

    if is_authenticated:
        response = await call_next(request)
        return response
    else:
        return time.time()


def get_ip_header(request: Request) -> str:
    ip = request.client.host if request.client else ""
    if not validIPAddress(ip):
        ip = request.headers.get("X_REAL_IP", "")
    elif not validIPAddress(ip):
        ip = request.headers.get("HTTP_X_FORWARDED_FOR", "")

    if mode != ProductionMode.PROD:
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
        return (
            "IPv4 or IPv6 address is in an incorrect format. "
            + "Dotted decimal for IPv4 or textual representation for IPv6 are required."
        )
    ip_addr = ip_address(IP)
    if ip_addr.is_link_local or ip_addr.is_loopback:
        return "You are on localhost"
    if ip_addr.is_private:
        return "You are on a private network"
    return ""


def lookup_ip_address(IP: str) -> IpLookupResponse:
    reader = geoip2.database.Reader(DB_PATH)
    response: City = reader.city(IP)
    return IpLookupResponse(
        country_code=response.country.iso_code,
        country_name=response.country.name,
        region_name=response.subdivisions.most_specific.name,
        city=response.city.name,
        ip=IP,
    )


@app.get("/geoip/")
@limiter.limit("5/minute")
def get_myip(request: Request) -> JSONResponse:
    ip = get_ip_header(request).strip()

    error = validate_ip(ip)
    if error != "":
        return JSONResponse({"detail": error})
    return JSONResponse(lookup_ip_address(ip).model_dump())


@app.get("/geoip/geolookup")
@limiter.limit("60/minute")
def get_geolookup(request: Request, ip: str) -> JSONResponse:
    ip = ip.strip()
    error = validate_ip(ip)
    if error != "":
        return JSONResponse({"detail": error})
    return JSONResponse(lookup_ip_address(ip).model_dump())
