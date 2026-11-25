"""Centralized runtime configuration: the single source of truth for env vars.

Real environment variables take precedence over `.env` values (pydantic-settings
handles both; no manual `load_dotenv()` needed).
"""
from __future__ import annotations

import multiprocessing
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        # Accept ENVIRONMENT=dev / Dev / DEV alike.
        return value.upper() if isinstance(value, str) else value

    @field_validator("ssl_cert", "ssl_key", mode="before")
    @classmethod
    def _empty_ssl_to_none(cls, value: object) -> object:
        # Treat empty .env values (e.g. "SSL_CERT =") as unset.
        return value or None

    @property
    def access_keys(self) -> list[str]:
        """Split the comma-separated ACCESS_KEY env var into a list."""
        return [k.strip() for k in self.access_key.split(",") if k.strip()]

    @property
    def log_level(self) -> str:
        return "debug" if self.environment == Environment.DEBUG else "info"

    @property
    def workers(self) -> int:
        return multiprocessing.cpu_count() * 2 + 1 if self.environment == Environment.PROD else 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
