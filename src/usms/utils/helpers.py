"""USMS Helper functions."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from usms.config.constants import BRUNEI_TZ, UNITS
from usms.exceptions.errors import (
    USMSFutureDateError,
    USMSInvalidParameterError,
    USMSUnsupportedStorageError,
)
from usms.storage.base_storage import BaseUSMSStorage
from usms.storage.csv_storage import CSVUSMSStorage
from usms.storage.sqlite_storage import SQLiteUSMSStorage
from usms.utils.logging_config import logger

# Date/time formats USMS uses, most specific first. Electricity meters report a full
# timestamp; water meters refresh daily and report a bare date.
DATETIME_FORMATS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y")


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


def dataframe_diff(
    old_dataframe: pd.DataFrame,
    new_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Return the diff (updated or new rows) between two dataframes."""
    old_dataframe = old_dataframe.reindex(new_dataframe.index)
    diff_mask = old_dataframe.ne(new_dataframe)
    new_dataframe = new_dataframe[diff_mask.any(axis=1)]
    return new_dataframe


def get_storage_manager(storage_type: str, storage_path: Path | None = None) -> BaseUSMSStorage:
    """Return the storage manager based on given storage type and path."""
    if "sql" in storage_type.lower():
        if storage_path is None:
            return SQLiteUSMSStorage(Path("usms.db"))
        return SQLiteUSMSStorage(storage_path)

    if "csv" in storage_type.lower():
        if storage_path is None:
            return CSVUSMSStorage(Path("usms.csv"))
        return CSVUSMSStorage(storage_path)

    raise USMSUnsupportedStorageError(storage_type)


def consumptions_storage_to_dataframe(
    consumptions: list[tuple[str, float, str]],
) -> pd.DataFrame:
    """Convert retrieved consumptions from persistent storage to dataframe."""
    hourly_consumptions = pd.DataFrame(
        consumptions,
        columns=["timestamp", "consumption", "last_checked"],
    )

    # last_checked timestamp
    hourly_consumptions["last_checked"] = pd.to_datetime(
        hourly_consumptions["last_checked"],
        unit="s",
    )
    hourly_consumptions["last_checked"] = hourly_consumptions["last_checked"].dt.tz_localize("UTC")
    hourly_consumptions["last_checked"] = hourly_consumptions["last_checked"].dt.tz_convert(
        "Asia/Brunei"
    )

    # timestamp as index
    hourly_consumptions["timestamp"] = pd.to_datetime(
        hourly_consumptions["timestamp"],
        unit="s",
    )
    hourly_consumptions["timestamp"] = hourly_consumptions["timestamp"].dt.tz_localize("UTC")
    hourly_consumptions["timestamp"] = hourly_consumptions["timestamp"].dt.tz_convert("Asia/Brunei")
    hourly_consumptions.set_index("timestamp", inplace=True)
    hourly_consumptions.index.name = None

    return hourly_consumptions


def parse_datetime(datetime_str: str) -> datetime:
    """
    Convert a given date/time string from USMS into a timezone-aware datetime object.

    Electricity meters report a full timestamp (e.g. 22/08/2026 08:15:00), but water
    meters only refresh once a day and report a bare date (e.g. 21/08/2026). Trying
    only the full format silently sent every water meter to the epoch fallback.

    The result is always tz-aware; USMS reports in Brunei local time. Returning a naive
    datetime here would make the caller's .astimezone() assume the *host* timezone,
    which is wrong anywhere but Brunei (e.g. a UTC container).

    Returns the epoch in Brunei time if the string matches no known format.
    """
    for datetime_format in DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(datetime_str.strip(), datetime_format)  # noqa: DTZ007
        except (ValueError, AttributeError):
            continue
        return parsed.replace(tzinfo=BRUNEI_TZ)

    return datetime.fromtimestamp(0, tz=BRUNEI_TZ)
