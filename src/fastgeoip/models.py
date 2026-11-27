from typing_extensions import Optional
from pydantic import BaseModel


class InternalServerErrorResponse(BaseModel):
    detail: str


class UnauthorizedResponse(BaseModel):
    error: str
    detail: str


class IpLookupResponse(BaseModel):
    country_code: Optional[str]
    country_name: Optional[str]
    region_name: Optional[str]
    city: Optional[str]
    ip: Optional[str]
