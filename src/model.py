from typing_extensions import Optional
from pydantic import BaseModel


class IpLookupResponse(BaseModel):
    country_code: Optional[str]
    country_name: Optional[str]
    region_name: Optional[str]
    city: Optional[str]
    ip: Optional[str]
