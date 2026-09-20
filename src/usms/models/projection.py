"""
USMS Month Projection Module.

This module defines the USMSMonthProjection class and the pure projection maths
used to estimate how a billing month will end: total consumption, its cost on
the meter's tariff, and when prepaid credit runs out.

The method is deliberately simple. The quantity being forecast is a *sum over
the remaining days of the month*, so day-to-day shape and weekday seasonality
average out and only the level estimate matters. Benchmarked against SES, Holt,
ETS with weekly seasonality, SARIMAX, gradient boosting, OLS with weekday
dummies and Prophet over two years of hourly data, this blend was the most
accurate of the lot (Prophet was by far the worst, since it fits yearly
seasonality to too short a series and extrapolates changepoints). Everything
here is plain arithmetic: no fitting, no numpy, and it runs on constrained
hardware such as a Raspberry Pi.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta

from usms.config.constants import PROJECTION_TRAILING_DAYS


@dataclass(frozen=True)
class USMSMonthProjection:
    """A projection of how the current billing month will end."""

    total_consumption: float
    daily_rate: float
    days_elapsed: int
    days_remaining: int

    # Filled in by USMSMeter.project_month(), which knows the tariff and the
    # meter's remaining credit; the pure projection leaves them unset.
    total_cost: float | None = None
    credit_runs_out_at: datetime | None = None


def project_month_consumption(
    daily_consumption: dict[date_type, float],
    now: datetime,
    trailing_days: int = PROJECTION_TRAILING_DAYS,
) -> USMSMonthProjection | None:
    """
    Project the current calendar month's total consumption.

    `daily_consumption` maps a date to that day's total consumption; it only
    needs to cover the recent past, and gaps are tolerated. Returns None when
    there is not yet a single complete day to learn from.

    The projected total is the month-to-date consumption plus the remaining days
    at a blended daily rate: half a trailing mean over `trailing_days` complete
    days, half the month-to-date rate. The trailing half keeps the estimate
    responsive early in the month, when few days have accrued; the
    month-to-date half anchors it later, once this month's own level is the
    better guide.
    """
    if not daily_consumption:
        return None

    today = now.date()
    days_in_month = monthrange(today.year, today.month)[1]

    # Today itself is excluded from the month-to-date figure: it is still
    # partial and would drag the rate down. It is counted as a remaining day.
    month_start = today.replace(day=1)
    elapsed = {
        day: consumption
        for day, consumption in daily_consumption.items()
        if month_start <= day < today
    }
    days_elapsed = len(elapsed)
    month_to_date = sum(elapsed.values())

    # Trailing mean over the most recent complete days, which may reach back
    # into the previous month - that is what makes day 1 projectable at all.
    complete = sorted(day for day in daily_consumption if day < today)
    if not complete:
        return None
    trailing = complete[-trailing_days:]
    trailing_rate = sum(daily_consumption[day] for day in trailing) / len(trailing)

    month_to_date_rate = month_to_date / days_elapsed if days_elapsed else trailing_rate
    daily_rate = 0.5 * trailing_rate + 0.5 * month_to_date_rate

    days_remaining = days_in_month - today.day + 1  # today is still to come
    return USMSMonthProjection(
        total_consumption=round(month_to_date + days_remaining * daily_rate, 3),
        daily_rate=round(daily_rate, 3),
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
    )


def credit_exhaustion_time(
    remaining_unit: float,
    daily_rate: float,
    now: datetime,
) -> datetime | None:
    """Return when prepaid credit runs out at the given daily rate."""
    if daily_rate <= 0 or remaining_unit is None or remaining_unit < 0:
        return None
    return now + timedelta(days=remaining_unit / daily_rate)
