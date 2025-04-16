"""
USMS Logging Module.

This module provides optional logging setup for the USMS application.
It avoids configuring log output unless explicitly requested, so it plays nicely
when imported in frameworks like Home Assistant which manage logging themselves.
"""

import logging
from datetime import datetime
from pathlib import Path

# Logger for the USMS package
logger = logging.getLogger("usms")
logger.propagate = True  # Let parent loggers handle output by default
logger.setLevel(logging.INFO)

# Default log format
LOG_FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(module)s.%(funcName)s:%(lineno)d] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)


def set_log_level(log_level: str) -> None:
    """Change the log level for all handlers attached to the logger."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


def enable_file_logging(log_file: str | Path, log_level: str = "INFO") -> None:
    """Enable file logging if a log file is specified."""
    if isinstance(log_file, str):
        log_file = Path(log_file)

    # Ensure directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    # Add separator for new runs
    logger.info("=" * 50)
    logger.info("New run started at %s", datetime.now().isoformat())  # noqa: DTZ005
    logger.info("=" * 50)


def init_console_logging(log_level: str = "INFO") -> None:
    """Set up console logging for standalone use."""
    if logger.hasHandlers():
        return  # Avoid double handlers

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.setLevel(console_handler.level)
    logger.propagate = False  # Prevent double logs
