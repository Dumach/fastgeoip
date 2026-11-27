from ipaddress import ip_address

from fastapi import Request

from fastgeoip.config import Environment, Settings


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
