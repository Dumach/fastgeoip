"""GeoIP lookups: the only module that imports geoip2."""

from functools import lru_cache

import geoip2.database
from geoip2.models import City

from fastgeoip.config import Settings
from fastgeoip.models import IpLookupResponse


@lru_cache
def get_reader(db_path: str) -> geoip2.database.Reader:
    """Open one reader per database path (the service runs a single worker).

    Import the module, not the Reader class: `geoip2.database.Reader` resolves
    at call time, so tests patching that attribute keep working. Such tests
    must also call `get_reader.cache_clear()` to avoid reusing a stale mock.
    """
    return geoip2.database.Reader(db_path)


def lookup_ip_address(IP: str, settings: Settings) -> IpLookupResponse:
    """Look up an IP address; GeoLite2 entries may lack any of the fields."""
    response: City = get_reader(str(settings.db_path)).city(IP)
    country = response.country
    subdivision = response.subdivisions.most_specific
    city = response.city
    return IpLookupResponse(
        country_code=country.iso_code if country else None,
        country_name=country.name if country else None,
        region_name=subdivision.name if subdivision else None,
        city=city.name if city else None,
        ip=IP,
    )
