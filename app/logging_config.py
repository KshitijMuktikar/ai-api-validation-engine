"""
Centralized logging: console + rotating file under ``logs/app.log``.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


def setup_logging() -> None:
    """Configure root logger for stdout and optional file output."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    log_path = Path(settings.log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        root.addHandler(file_handler)
    except OSError as e:
        root.warning("Could not attach file log handler to %s: %s", log_path, e)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
