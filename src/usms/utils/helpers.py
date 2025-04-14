"""USMS Helper functions."""

from datetime import datetime

import pandas as pd

from usms.config.constants import BRUNEI_TZ
from usms.exceptions.errors import USMSFutureDateError
from usms.utils.logging_config import logger


def sanitize_date(date: datetime) -> datetime:
    """Check given date and attempt to sanitize it, unless its in the future."""
    # Make sure given date has timezone info
    if not date.tzinfo:
        logger.debug(f"Given date has no timezone, assuming {BRUNEI_TZ}")
        date = date.replace(tzinfo=BRUNEI_TZ)

    # Make sure the given day is not in the future
    if date > datetime.now(tz=BRUNEI_TZ):
        raise USMSFutureDateError(date)

    return datetime(year=date.year, month=date.month, day=date.day, tzinfo=BRUNEI_TZ)


def new_consumptions_dataframe(unit: str, freq: str) -> pd.DataFrame:
    """Return an empty dataframe with proper datetime index and column name."""
    new_dataframe = pd.DataFrame(
        dtype=float,
        columns=[unit, "last_checked"],
        index=pd.DatetimeIndex(
            [],
            tz=BRUNEI_TZ,
            freq="h",
        ),
    )
    new_dataframe["last_checked"] = pd.to_datetime(new_dataframe["last_checked"]).dt.tz_localize(
        BRUNEI_TZ
    )
    return new_dataframe
