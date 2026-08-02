"""Logging configuration."""

from __future__ import annotations

import logging
from logging.config import dictConfig


def configure_logging(level: str = "INFO") -> None:
    """Configure process-wide standard-library logging."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": ("%(asctime)s | %(levelname)s | %(name)s | %(message)s"),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                },
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "aiogram.event": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        },
    )
    logging.captureWarnings(True)
