from enum import Enum

import uvicorn
import os
from dotenv import load_dotenv
from config.logging import log_config

load_dotenv()


class ProductionMode(Enum):
    DEV = 1
    DEBUG = 2
    PROD = 3


def get_workers(mode: ProductionMode) -> int:
    """
    Get count of uvicorn workers.

    When PROD it utilizes the max count of cores * 2 + 1.
    WORKER_COUNT env var can override it.
    """
    import multiprocessing

    count: int = 1
    if mode == ProductionMode.PROD:
        count = (multiprocessing.cpu_count() * 2) + 1
    count = int(os.environ.get("WORKER_COUNT", count))
    return count


env = os.environ.get("ENVIRONMENT", "PROD").strip().lower()
mode: ProductionMode = ProductionMode.PROD
match env:
    case "dev":
        mode = ProductionMode.DEV
    case "debug":
        mode = ProductionMode.DEBUG
    case _:
        mode = ProductionMode.PROD

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8080))

SSL_CERT = os.environ.get("SSL_CERT")
SSL_KEY = os.environ.get("SSL_KEY")
ACCESS_KEYS = [k.strip() for k in os.environ.get("ACCESS_KEY", "").split(",") if k.strip()]

log_level = "info"
if mode == ProductionMode.DEBUG:
    log_level = "debug"

if __name__ == "__main__":
    uvicorn.run(
        "src.app:app",
        host=HOST,
        port=PORT,
        log_level=log_level,
        log_config=log_config,
        reload=mode == ProductionMode.DEV,
        ssl_certfile=SSL_CERT,
        ssl_keyfile=SSL_KEY,
        workers=get_workers(mode),
        proxy_headers=True,  # Trust X-Forwarded headers from reverse proxy
        forwarded_allow_ips="*",  # Allow forwarded headers from any IP
    )
