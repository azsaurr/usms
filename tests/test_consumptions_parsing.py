"""Test how UsageHistory rows are mapped onto timestamps."""

from datetime import datetime, timedelta

import pytest

from usms.config.constants import BRUNEI_TZ
from usms.services.sync.meter import USMSMeter

HOURS_IN_DAY = 24


def _meter(unit: str = "kWh") -> USMSMeter:
    """Return a bare meter, bypassing the service constructor."""
    meter = USMSMeter.__new__(USMSMeter)
    meter.no = "55014488"
    meter.unit = unit
    return meter


def _grid(values: list[float], *, first_label: int = 1) -> str:
    """
    Return markup shaped like a UsageHistory grid.

    The row id carries a zero-based index while the first cell shows a label
    starting at 1, which is the discrepancy the mapping has to account for.
    """
    rows = "".join(
        f'<tr id="ASPxPageControl1_grid_DXDataRow{index}">'
        f"<td>{index + first_label}</td><td>{value}</td></tr>"
        for index, value in enumerate(values)
    )
    return f"<table>{rows}</table>"


def test_hourly_rows_stay_inside_the_requested_day() -> None:
    """
    Test that a full day of hourly rows spans 00:00-23:00 of that day.

    Mapping row 0 to 23:00 of the previous day both misdated the reading and
    poisoned the cache: a later fetch for that day found the stray timestamp,
    concluded it already had data, and returned one row instead of 24.
    """
    date = datetime(2026, 8, 20, tzinfo=BRUNEI_TZ)
    consumptions = _meter()._parse_hourly_consumptions_response(  # noqa: SLF001
        _grid([1.0] * HOURS_IN_DAY).encode(),
        date,
    )

    assert len(consumptions) == HOURS_IN_DAY
    assert min(consumptions) == date
    assert max(consumptions) == date + timedelta(hours=23)
    assert all(timestamp.date() == date.date() for timestamp in consumptions)


def test_hourly_first_row_is_midnight() -> None:
    """Test that the row labelled "1" is the 00:00-01:00 slot."""
    date = datetime(2026, 8, 20, tzinfo=BRUNEI_TZ)
    consumptions = _meter()._parse_hourly_consumptions_response(  # noqa: SLF001
        _grid([6.514, 5.757]).encode(),
        date,
    )

    assert consumptions[date] == pytest.approx(6.514)
    assert consumptions[date + timedelta(hours=1)] == pytest.approx(5.757)


def test_hourly_timestamps_are_timezone_aware() -> None:
    """Test that timestamps keep the Brunei timezone of the requested date."""
    date = datetime(2026, 8, 20, tzinfo=BRUNEI_TZ)
    consumptions = _meter()._parse_hourly_consumptions_response(  # noqa: SLF001
        _grid([1.0, 2.0]).encode(),
        date,
    )

    assert all(timestamp.tzinfo is not None for timestamp in consumptions)


def test_daily_rows_map_to_days_of_the_month() -> None:
    """Test that the zero-based row index becomes the correct day of the month."""
    date = datetime(2026, 8, 15, tzinfo=BRUNEI_TZ)
    consumptions = _meter("m³")._parse_daily_consumptions_response(  # noqa: SLF001
        _grid([3.0, 4.0, 5.0]).encode(),
        date,
    )

    assert sorted(consumptions) == [
        datetime(2026, 8, 1, tzinfo=BRUNEI_TZ),
        datetime(2026, 8, 2, tzinfo=BRUNEI_TZ),
        datetime(2026, 8, 3, tzinfo=BRUNEI_TZ),
    ]
    assert consumptions[datetime(2026, 8, 1, tzinfo=BRUNEI_TZ)] == pytest.approx(3.0)


def test_empty_grid_yields_no_consumptions() -> None:
    """Test that a report with no rows parses to an empty mapping."""
    date = datetime(2026, 8, 20, tzinfo=BRUNEI_TZ)

    assert (
        _meter()._parse_hourly_consumptions_response(b"<table></table>", date) == {}  # noqa: SLF001
    )
