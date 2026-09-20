"""
USMS constants.

This module defines the constants for this USMS package.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from usms.models.tariff import USMSTariff, USMSTariffTier

BRUNEI_TZ = ZoneInfo("Asia/Brunei")

ELECTRIC_UNIT = "kWh"
WATER_UNIT = "m³"

# Residential tariffs only, as published at https://www.usms.com.bn/web/tariffs/.
# Commercial rates are structured differently - electricity is billed per kVA of
# capacity and water at a flat rate per category - so they are not expressible as
# these consumption tiers. calculate_total_cost() warns when it sees a meter that
# is not residential.
ELECTRIC_TARIFF = USMSTariff(
    [
        USMSTariffTier(1, 600, 0.01),
        USMSTariffTier(601, 2000, 0.08),
        USMSTariffTier(2001, 4000, 0.10),
        USMSTariffTier(4001, float("inf"), 0.12),
    ]
)
WATER_TARIFF = USMSTariff(
    [
        USMSTariffTier(1, 54.54, 0.11),
        USMSTariffTier(54.54, float("inf"), 0.44),
    ]
)

UNITS = {
    "ELECTRIC": ELECTRIC_UNIT,
    "WATER": WATER_UNIT,
}
TARIFFS = {
    "ELECTRIC": ELECTRIC_TARIFF,
    "WATER": WATER_TARIFF,
}

# Rolling window (in days) the month projection averages over. Seven days is
# long enough to smooth daily noise yet short enough to follow a change in
# habits; it was the best of 7/14/28 when backtested over two years of data.
PROJECTION_TRAILING_DAYS = 7

UPDATE_INTERVAL = timedelta(seconds=60 * 60)
REFRESH_INTERVAL = timedelta(seconds=60 * 15)

# Per-meter Top Up page. Payment itself redirects to the bank's secure site, so this
# is only ever handed to the user, never submitted programmatically.
TOPUP_URL = "https://www.usms.com.bn/SmartMeter/Payment/WebForm2"

# Upper bound on how far back the earliest-date search will probe. USMS keeps hourly
# data until the meter's commissioning date rather than for a rolling window; this is
# only a backstop so the search cannot run away.
MAX_HISTORY_DAYS = 1024
