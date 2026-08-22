"""USMS Meter Module."""

import base64
from dataclasses import dataclass
from datetime import datetime

from usms.config.constants import BRUNEI_TZ, TOPUP_URL
from usms.utils.helpers import parse_currency, parse_datetime


@dataclass
class USMSMeter:
    """Represents a USMS meter."""

    """USMS Meter class attributes."""
    address: str
    kampong: str
    mukim: str
    district: str
    postcode: str

    no: str
    id: str  # base64 encoded meter no

    type: str
    # customer_type: str  # currently not fetched  # noqa: ERA001

    remaining_unit: float
    remaining_credit: float

    last_update: datetime

    status: str

    """Details from the meter's Top Up page, populated by fetch_payment_info()."""
    customer_type: str | None = None
    debt_clearance_model: str | None = None
    total_debt_owing: float = 0.0
    monthly_debt_amount: float = 0.0
    debt_balance_remaining: float = 0.0
    debt_repayment_period: str | None = None
    debt_period_remaining: str | None = None

    def update_from_json(self, data: dict[str, str]) -> None:
        """Update base attributes from a json/dict data."""
        allowed = {"status", "address", "kampong", "mukim", "district", "postcode"}
        for key, value in data.items():
            if key in allowed:
                setattr(self, key, value)

        no = data.get("no", "")
        if no:
            self.no = no
            self.id = base64.b64encode(no.encode()).decode()

        remaining_unit = data.get("remaining_unit", "").split()
        if remaining_unit:
            self.remaining_unit = float(remaining_unit[0].replace(",", ""))
            self.unit = remaining_unit[-1]
            self.type = "Water" if remaining_unit[-1] == "m³" else "Electricity"

        remaining_credit = data.get("remaining_credit", "").split("$")[-1]
        if remaining_credit:
            self.remaining_credit = float(remaining_credit.replace(",", ""))

        self.last_update = parse_datetime(data.get("last_update", "")).astimezone(BRUNEI_TZ)

    def update_from_payment_json(self, data: dict[str, str]) -> None:
        """Update the debt and customer attributes from parsed Top Up page data."""
        for key in ("customer_type", "debt_clearance_model"):
            if data.get(key):
                setattr(self, key, data[key])

        for key in ("debt_repayment_period", "debt_period_remaining"):
            value = (data.get(key) or "").strip()
            # USMS renders "not applicable" as a bare dash or an empty cell.
            setattr(self, key, None if value in ("", "-") else value)

        for key in ("total_debt_owing", "monthly_debt_amount", "debt_balance_remaining"):
            setattr(self, key, parse_currency(data.get(key)))

    @property
    def is_active(self) -> bool:
        """Return True if the meter status is active."""
        return self.status == "ACTIVE"

    @property
    def has_debt(self) -> bool:
        """Return True if there is any outstanding debt on this meter."""
        return self.total_debt_owing > 0 or self.debt_balance_remaining > 0

    @property
    def topup_url(self) -> str:
        """
        Return the USMS Top Up page for this meter.

        Topping up cannot be automated: the form hands off to the bank's secure site
        for card entry, so this URL is meant to be opened by the user.
        """
        return f"{TOPUP_URL}?p={self.id}&s=h"

    @property
    def is_water(self) -> bool:
        """Return True if this is a water meter."""
        return self.type == "Water"

    @property
    def supports_hourly_consumptions(self) -> bool:
        """
        Return True if USMS exposes hourly consumptions for this meter.

        Water meters only refresh once every 24 hours, and their UsageHistory report
        offers no "Hourly (Max 1 day)" option at all - only Monthly, Daily and Summary.
        Requesting hourly data for one always comes back empty.
        """
        return not self.is_water
