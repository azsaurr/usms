"""
USMS Logging Module.

This module configures and initializes logging for the USMS application.
It provides a centralized logger instance that can be imported and used
across different modules to ensure consistent logging behavior.
"""

import logging
from datetime import datetime
from pathlib import Path

# Create a logger for the package
logger = logging.getLogger("usms")
logger.setLevel(logging.INFO)  # Default to DEBUG level

# Log format
LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)-8s] [%(module)s.%(funcName)s:%(lineno)d] - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

# Console handler (stdout)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def set_log_level(log_level: str) -> None:
    """Change the log level for stdout dynamically."""
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))


# Function to enable file logging (only if explicitly configured)
def enable_file_logging(log_file: str, log_level: str) -> None:
    """Enable file logging if a log file is specified."""
    if not log_file:
        return  # Don't log to a file unless explicitly set

    if isinstance(log_file, str):
        log_file = Path(log_file)
    log_dir = log_file.parent

    # Ensure directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add separator for new runs
    logger.info("=" * 50)
    logger.info("New run started at %s", datetime.now().isoformat())  # noqa: DTZ005
    logger.info("=" * 50)
