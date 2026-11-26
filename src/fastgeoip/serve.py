"""Uvicorn entrypoint: load settings and run the app."""

import uvicorn
from pydantic import ValidationError

from fastgeoip.config import Environment, get_settings
from fastgeoip.logging_config import build_log_config


def serve() -> None:
    """Load settings and start the uvicorn server."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        # One-line error instead of a pydantic traceback.
        raise SystemExit(f"Configuration error:\n{exc}") from exc

    uvicorn.run(
        "fastgeoip.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        log_config=build_log_config(settings.log_path, settings.log_level),
        reload=settings.environment == Environment.DEV,
        ssl_certfile=settings.ssl_cert,
        ssl_keyfile=settings.ssl_key,
        workers=settings.workers,
        proxy_headers=True,  # Trust X-Forwarded headers from reverse proxy
        forwarded_allow_ips="*",  # Allow forwarded headers from any IP (tightened in a later phase)
    )


if __name__ == "__main__":
    serve()
