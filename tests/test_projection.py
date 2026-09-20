"""Test the month projection maths."""

from datetime import date, datetime, timedelta

from usms.config.constants import BRUNEI_TZ, TARIFFS
from usms.models.projection import (
    USMSMonthProjection,
    credit_exhaustion_time,
    project_month_consumption,
)
from usms.services.meter import BaseUSMSMeter


def test_steady_rate_projects_to_month_total() -> None:
    """Test a steady daily rate projects back to the expected month total."""
    daily = {date(2026, 9, d): 100.0 for d in range(1, 10)}
    now = datetime(2026, 9, 10, 12, 0, tzinfo=BRUNEI_TZ)

    projection = project_month_consumption(daily, now)

    assert isinstance(projection, USMSMonthProjection)
    assert projection.daily_rate == 100.0
    assert projection.total_consumption == 3000.0
    assert projection.days_elapsed == 9
    assert projection.days_remaining == 21


def test_first_of_month_uses_trailing_window() -> None:
    """Test day-1 falls back to the trailing mean, since nothing has accrued."""
    daily = {date(2026, 8, d): 80.0 for d in range(1, 31)}
    now = datetime(2026, 9, 1, tzinfo=BRUNEI_TZ)

    projection = project_month_consumption(daily, now)

    assert projection.days_elapsed == 0
    assert projection.daily_rate == 80.0
    assert projection.total_consumption == 80.0 * 30


def test_blend_sits_between_its_two_rates() -> None:
    """Test the blend lands between the trailing and month-to-date rates."""
    # This month runs at 50/day; the week before it ran at 150/day.
    daily = {date(2026, 8, d): 150.0 for d in range(25, 32)}
    daily |= {date(2026, 9, d): 50.0 for d in range(1, 4)}
    now = datetime(2026, 9, 4, tzinfo=BRUNEI_TZ)

    projection = project_month_consumption(daily, now)

    assert 50.0 < projection.daily_rate < 150.0


def test_returns_none_without_a_complete_day() -> None:
    """Test the projection is None until at least one full prior day exists."""
    now = datetime(2026, 9, 10, tzinfo=BRUNEI_TZ)

    assert project_month_consumption({}, now) is None
    assert project_month_consumption({date(2026, 9, 10): 40.0}, now) is None


def test_gaps_in_history_are_tolerated() -> None:
    """Test a sparse history still projects from the days that are present."""
    daily = {date(2026, 9, 1): 90.0, date(2026, 9, 5): 110.0}
    now = datetime(2026, 9, 6, tzinfo=BRUNEI_TZ)

    projection = project_month_consumption(daily, now)

    assert projection.days_elapsed == 2
    assert projection.daily_rate == 100.0


def test_credit_exhaustion_time() -> None:
    """Test the credit runway divides remaining units by the daily rate."""
    now = datetime(2026, 9, 10, tzinfo=BRUNEI_TZ)

    assert credit_exhaustion_time(1000.0, 100.0, now) == now + timedelta(days=10)
    assert credit_exhaustion_time(1000.0, 0.0, now) is None
    assert credit_exhaustion_time(-5.0, 100.0, now) is None


class _StubMeter(BaseUSMSMeter):
    """Minimal meter standing in for a real one, to exercise project_month()."""

    def __init__(self, meter_type: str, remaining_unit: float) -> None:
        self.type = meter_type
        self.remaining_unit = remaining_unit


def test_meter_project_month_prices_and_dates_the_projection() -> None:
    """Test the meter enriches the projection with cost and a credit runway."""
    meter = _StubMeter("Electricity", remaining_unit=1000.0)
    daily = {date(2026, 9, d): 100.0 for d in range(1, 10)}
    now = datetime(2026, 9, 10, tzinfo=BRUNEI_TZ)

    projection = meter.project_month(daily, now)

    assert projection.total_consumption == 3000.0
    # 3000 kWh on the residential electricity tariff.
    assert projection.total_cost == TARIFFS["ELECTRIC"].calculate_cost(3000.0)
    # 1000 kWh left at 100/day.
    assert projection.credit_runs_out_at == now + timedelta(days=10)


def test_meter_project_month_without_a_known_tariff() -> None:
    """Test an unrecognised meter type still projects, just without a cost."""
    meter = _StubMeter("Gas", remaining_unit=0.0)
    daily = {date(2026, 9, d): 10.0 for d in range(1, 10)}

    projection = meter.project_month(daily, datetime(2026, 9, 10, tzinfo=BRUNEI_TZ))

    assert projection.total_consumption > 0
    assert projection.total_cost is None


def test_daily_consumptions_from_collapses_hourly() -> None:
    """Test hourly consumptions roll up into per-day totals."""
    hourly = {datetime(2026, 9, 1, hour, tzinfo=BRUNEI_TZ): 2.0 for hour in range(24)}
    hourly[datetime(2026, 9, 2, 0, tzinfo=BRUNEI_TZ)] = 5.0

    daily = BaseUSMSMeter.daily_consumptions_from(hourly)

    assert daily[date(2026, 9, 1)] == 48.0
    assert daily[date(2026, 9, 2)] == 5.0
