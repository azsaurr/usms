"""USMS Helper functions."""

import asyncio
import ssl
from datetime import datetime
from pathlib import Path

import pandas as pd

from usms.config.constants import BRUNEI_TZ, UNITS
from usms.exceptions.errors import USMSFutureDateError, USMSInvalidParameterError
from usms.storage.csv_storage import CSVStorage
from usms.storage.sqlite_storage import SQLiteStorage
from usms.utils.logging_config import logger


def sanitize_date(date: datetime) -> datetime:
    """Check given date and attempt to sanitize it, unless its in the future."""
    # Make sure given date has timezone info
    if not date.tzinfo:
        logger.debug(f"Given date has no timezone, assuming {BRUNEI_TZ}")
        date = date.astimezone()
    date = date.astimezone(BRUNEI_TZ)

    # Make sure the given day is not in the future
    if date > datetime.now(tz=BRUNEI_TZ):
        raise USMSFutureDateError(date)

    return datetime(year=date.year, month=date.month, day=date.day, tzinfo=BRUNEI_TZ)


def new_consumptions_dataframe(unit: str, freq: str) -> pd.DataFrame:
    """Return an empty dataframe with proper datetime index and column name."""
    # check for valid parameters
    if unit not in UNITS.values():
        raise USMSInvalidParameterError(unit, UNITS.values())

    if freq not in ("h", "D"):
        raise USMSInvalidParameterError(freq, ("h", "D"))

    new_dataframe = pd.DataFrame(
        dtype=float,
        columns=[unit, "last_checked"],
        index=pd.DatetimeIndex(
            [],
            tz=BRUNEI_TZ,
            freq=freq,
        ),
    )
    new_dataframe["last_checked"] = pd.to_datetime(new_dataframe["last_checked"]).dt.tz_localize(
        datetime.now().astimezone().tzinfo
    )
    return new_dataframe


async def create_ssl_context() -> ssl.SSLContext:
    """Run SSL context creation in a thread to avoid blocking the event loop."""

    def setup_ssl():
        ctx = ssl.create_default_context()
        try:
            import certifi

            ctx.load_verify_locations(cafile=certifi.where())
        except ImportError:
            pass  # fallback to system defaults
        return ctx

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, setup_ssl)


def dataframe_diff(
    old_dataframe: pd.DataFrame,
    new_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Return the diff (updated or new rows) between two dataframes."""
    old_dataframe = old_dataframe.reindex(new_dataframe.index)
    diff_mask = old_dataframe.ne(new_dataframe)
    new_dataframe = new_dataframe[diff_mask.any(axis=1)]
    return new_dataframe


def get_storage(
    storage_type: str, storage_path: Path | None = None
) -> CSVStorage | SQLiteStorage | None:
    """Return the storage manager based on given storage type and path."""
    if "sql" in storage_type.lower():
        if storage_path is None:
            return SQLiteStorage(Path("usms.db"))
        return SQLiteStorage(storage_path)

    if "csv" in storage_type.lower():
        if storage_path is None:
            return CSVStorage(Path("usms.csv"))
        return CSVStorage(storage_path)

    msg = "Unsupported storage type."
    raise ValueError(msg)
