"""USMS Helper functions."""

from datetime import datetime
from pathlib import Path

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
        logger.debug("Given date has no timezone, assuming %s", BRUNEI_TZ)
        date = date.astimezone()
    date = date.astimezone(BRUNEI_TZ)

    # Make sure the given day is not in the future
    if date > datetime.now(tz=BRUNEI_TZ):
        raise USMSFutureDateError(date)

    return datetime(year=date.year, month=date.month, day=date.day, tzinfo=BRUNEI_TZ)


def new_consumptions(unit: str, freq: str) -> dict[datetime, float]:
    """
    Validate the given unit/frequency pair and return an empty consumptions mapping.

    Consumptions are held as {timestamp: consumption}, ordered chronologically. Unlike
    the dataframe this replaces, gaps are simply absent rather than materialised as
    NaN rows, so summing and iterating skip them naturally.
    """
    if unit not in UNITS.values():
        raise USMSInvalidParameterError(unit, UNITS.values())

    if freq not in ("h", "D"):
        raise USMSInvalidParameterError(freq, ("h", "D"))

    return {}


def merge_consumptions(
    new_consumptions_map: dict[datetime, float],
    old_consumptions_map: dict[datetime, float],
) -> dict[datetime, float]:
    """Merge two consumptions mappings chronologically, preferring the newer values."""
    return dict(sorted({**old_consumptions_map, **new_consumptions_map}.items()))


def consumptions_diff(
    old_consumptions_map: dict[datetime, float],
    new_consumptions_map: dict[datetime, float],
) -> dict[datetime, float]:
    """Return the entries of the new mapping that are absent from or differ from the old."""
    return {
        timestamp: consumption
        for timestamp, consumption in new_consumptions_map.items()
        if old_consumptions_map.get(timestamp) != consumption
    }


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


def consumptions_from_storage(
    consumptions: list[tuple[str, float, str]],
) -> tuple[dict[datetime, float], dict[datetime, datetime]]:
    """
    Convert consumptions retrieved from persistent storage into in-memory mappings.

    Storage holds epoch seconds; both returned mappings are keyed by Brunei-local
    timestamps. Returns the consumptions and their last_checked times separately.
    """
    consumptions_map: dict[datetime, float] = {}
    last_checked_map: dict[datetime, datetime] = {}

    for timestamp, consumption, last_checked in consumptions:
        moment = datetime.fromtimestamp(int(timestamp), tz=BRUNEI_TZ)
        consumptions_map[moment] = float(consumption)
        last_checked_map[moment] = datetime.fromtimestamp(int(last_checked), tz=BRUNEI_TZ)

    return dict(sorted(consumptions_map.items())), last_checked_map


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
