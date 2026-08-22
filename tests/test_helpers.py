"""Test helper functions."""

from datetime import datetime

import pytest

from usms.config.constants import BRUNEI_TZ
from usms.utils.helpers import parse_datetime

EPOCH = datetime.fromtimestamp(0, tz=BRUNEI_TZ)


@pytest.mark.parametrize(
    ("datetime_str", "expected"),
    [
        # Electricity meters report a full timestamp.
        ("22/08/2026 08:15:00", datetime(2026, 8, 22, 8, 15, 0, tzinfo=BRUNEI_TZ)),
        ("02/06/2025 17:30:00", datetime(2025, 6, 2, 17, 30, 0, tzinfo=BRUNEI_TZ)),
        # Water meters refresh daily and report a bare date. These used to fall
        # through to the epoch, so every water meter reported 1970-01-01.
        ("21/08/2026", datetime(2026, 8, 21, 0, 0, 0, tzinfo=BRUNEI_TZ)),
        ("01/01/2025", datetime(2025, 1, 1, 0, 0, 0, tzinfo=BRUNEI_TZ)),
        # Surrounding whitespace is tolerated.
        ("  21/08/2026  ", datetime(2026, 8, 21, 0, 0, 0, tzinfo=BRUNEI_TZ)),
        # Unparseable input still falls back to the epoch.
        ("", EPOCH),
        ("not a date", EPOCH),
        ("2026-08-21", EPOCH),
        (None, EPOCH),
    ],
)
def test_parse_datetime(datetime_str, expected) -> None:
    """Test that both USMS date formats parse, and junk falls back to the epoch."""
    assert parse_datetime(datetime_str) == expected


@pytest.mark.parametrize(
    "datetime_str",
    ["22/08/2026 08:15:00", "21/08/2026", "", "not a date"],
)
def test_parse_datetime_is_always_aware(datetime_str) -> None:
    """A naive result would make callers assume the host timezone, not Brunei's."""
    assert parse_datetime(datetime_str).tzinfo is not None
