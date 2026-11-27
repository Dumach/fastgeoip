"""Application settings loaded from the environment and .env."""

from __future__ import annotations

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
    ssl_cert: str | None = None
    ssl_key: str | None = None
    access_key: str = ""
    log_path: Path = Path("./logs")
    # Optional override for the GeoLite2-City database location (DB_PATH env var).
    db_path: Path = Path("./db/GeoLite2-City.mmdb")
    # Peers uvicorn trusts for X-Forwarded-For rewriting (FORWARDED_ALLOW_IPS env var).
    forwarded_allow_ips: str = "127.0.0.1,::1"

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        """Accept ENVIRONMENT=dev / Dev / DEV alike."""
        return value.upper() if isinstance(value, str) else value

    @field_validator("ssl_cert", "ssl_key", mode="before")
    @classmethod
    def _empty_ssl_to_none(cls, value: object) -> object:
        """Treat empty .env values (e.g. "SSL_CERT =") as unset."""
        return value or None

    @model_validator(mode="after")
    def _fail_fast(self) -> Settings:
        """Fail fast on misconfiguration instead of 403/HTTPS errors mid-request."""
        if self.environment in (Environment.DEBUG, Environment.PROD) and not self.access_keys:
            raise ValueError("ACCESS_KEY must be set (comma-separated keys) when ENVIRONMENT is PROD or DEBUG")
        if bool(self.ssl_cert) != bool(self.ssl_key):
            raise ValueError("SSL_CERT and SSL_KEY must be set together")
        for label, path in (("SSL_CERT", self.ssl_cert), ("SSL_KEY", self.ssl_key)):
            if path and not Path(path).is_file():
                raise ValueError(f"{label} points to a missing file: {path}")
        return self

    @property
    def access_keys(self) -> list[str]:
        """Split the comma-separated ACCESS_KEY env var into a list."""
        return [k.strip() for k in self.access_key.split(",") if k.strip()]

    @property
    def log_level(self) -> str:
        return "debug" if self.environment == Environment.DEBUG else "info"

    @property
    def workers(self) -> int:
        """
        PROD scales to the CPU core count; other modes use a single worker.
        we used too much memory and for the number of requests a single worker is enough

        Formula: return multiprocessing.cpu_count() if self.environment == Environment.PROD else 1
        """
        return 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
