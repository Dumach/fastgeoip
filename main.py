"""Launcher: read config once, start uvicorn."""
import uvicorn

from config.logging import build_log_config
from src.config import Environment, get_settings


def main() -> None:
    settings = get_settings()
    settings.log_path.mkdir(parents=True, exist_ok=True)  # log_config handlers open access.log at startup
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        log_config=build_log_config(settings.log_path),
        reload=settings.environment == Environment.DEV,
        ssl_certfile=settings.ssl_cert,
        ssl_keyfile=settings.ssl_key,
        workers=settings.workers,
        proxy_headers=True,  # Trust X-Forwarded headers from reverse proxy
        forwarded_allow_ips="*",  # Allow forwarded headers from any IP (tightened in a later phase)
    )


if __name__ == "__main__":
    main()
