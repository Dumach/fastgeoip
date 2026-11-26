"""Uvicorn logging configuration: console output plus a rotating access log."""

from __future__ import annotations

from pathlib import Path


def build_log_config(log_path: Path, level: str = "info") -> dict:
    """Build uvicorn's dictConfig; creates log_path if needed."""
    Path(log_path).mkdir(parents=True, exist_ok=True)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s - %(levelprefix)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": False,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s - %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',  # noqa: E501
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": False,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "formatter": "default",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": f"{log_path}/access.log",
                "maxBytes": 1_048_576,  # 1 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default", "file"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {
                "handlers": ["access", "file"],
                "level": "INFO",
                "propagate": False,
            },
            # App logs (e.g. parse failure tracebacks); mirrors the handlers
            # the uvicorn.default logger used to provide.
            "fastpostal": {
                "handlers": ["default", "file"],
                "level": level.upper(),  # dictConfig wants level names, e.g. "INFO"
                "propagate": False,
            },
        },
    }
