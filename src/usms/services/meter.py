"""Base USMS Meter Service."""

import base64
from abc import ABC
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Union
from zoneinfo import ZoneInfo

import pandas as pd

from usms.config.constants import BRUNEI_TZ, REFRESH_INTERVAL, TARIFFS, UNITS
from usms.models.meter import USMSMeter as USMSMeterModel
from usms.utils.decorators import requires_init
from usms.utils.helpers import new_consumptions_dataframe, sanitize_date
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.core.client import AsyncUSMSClient, USMSClient
    from usms.services.async_.account import AsyncUSMSAccount
    from usms.services.sync.account import USMSAccount


class BaseUSMSMeter(ABC, USMSMeterModel):
    """Base USMS Meter Service to be inherited."""

    _account: Union["USMSAccount", "AsyncUSMSAccount"]
    session: Union["USMSClient", "AsyncUSMSClient"]

    earliest_consumption_date: datetime
    hourly_consumptions: pd.DataFrame
    daily_consumptions: pd.DataFrame

    def __init__(self, account: Union["USMSAccount", "AsyncUSMSAccount"]) -> None:
        """Set initial class variables."""
        self._account = account
        self.session = account.session
        self.storage_manager = account.storage_manager

        self._initialized = False

    def initialize(self):
        """Set initial values for class variables."""
        self.earliest_consumption_date = None

        self._initialized = True

        self.hourly_consumptions = new_consumptions_dataframe(self.get_unit(), "h")
        self.daily_consumptions = new_consumptions_dataframe(self.get_unit(), "D")

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        self.no = data.get("no", "")
        if self.no:
            self.id = base64.b64encode(self.no.encode()).decode()
        else:
            self.id = ""

        self.type = "Water" if "Water" in data.get("type", "") else "Electricity"

        self.status = data.get("status", "") == "ACTIVE"

        self.address = data.get("address", "")
        self.kampong = data.get("kampong", "")
        self.mukim = data.get("mukim", "")
        self.district = data.get("district", "")
        self.postcode = data.get("postcode", "")

        self.remaining_unit = float(data.get("remaining_unit", "").split()[0].replace(",", ""))

        self.remaining_credit = float(
            data.get("remaining_credit", "").split("$")[-1].replace(",", "")
        )

        self.last_update = data.get("last_update", "")
        if self.last_update == "" or self.last_update is None:
            self.last_update = datetime.fromtimestamp(0).astimezone()
        else:
            date = self.last_update.split()[0].split("/")
            time = self.last_update.split()[1].split(":")
            self.last_update = datetime(
                int(date[2]),
                int(date[1]),
                int(date[0]),
                hour=int(time[0]),
                minute=int(time[1]),
                second=int(time[2]),
                tzinfo=BRUNEI_TZ,
            )

    def _build_hourly_consumptions_payload(self, date: datetime) -> dict:
        """Build and return the payload for the hourly consumptions page from a given date."""
        epoch = date.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)

        # build payload
        payload = {}
        payload["cboType_VI"] = "3"
        payload["cboType"] = "Hourly (Max 1 day)"

        payload["btnRefresh"] = ["Search", ""]
        payload["cboDateFrom"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        payload["cboDateTo$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"

        return payload

    def _build_daily_consumptions_payload(self, date: datetime) -> dict:
        """Build and return the payload for the daily consumptions page from a given date."""
        date_from = datetime(
            date.year,
            date.month,
            1,
            8,
            0,
            0,
            tzinfo=BRUNEI_TZ,
        )
        epoch_from = date_from.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        now = sanitize_date(datetime.now().astimezone())
        # check if given month is still ongoing
        if date.year == now.year and date.month == now.month:
            # then get consumption up until yesterday only
            date = now - timedelta(days=1)
        else:
            # otherwise get until the last day of the month
            next_month = date.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            date = date.replace(day=last_day.day)
        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch_to = date.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        payload = {}
        payload["cboType_VI"] = "1"
        payload["cboType"] = "Daily (Max 1 month)"
        payload["btnRefresh"] = "Search"
        payload["cboDateFrom"] = f"01/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch_from}&quot;" + "}"
        payload["cboDateTo$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch_to}&quot;" + "}"

        return payload

    @requires_init
    def get_hourly_consumptions(self, date: datetime) -> pd.Series:
        """Check and return consumptions found for a given day."""
        day_consumption = self.hourly_consumptions[
            self.hourly_consumptions.index.date == date.date()
        ]
        # Check if consumption for this date was already fetched
        if not day_consumption.empty:
            now = datetime.now().astimezone()

            last_checked = day_consumption["last_checked"].min()
            time_since_last_checked = now - last_checked

            time_since_given_date = now - date

            # If not enough time has passed since the last check
            if (time_since_last_checked < REFRESH_INTERVAL) or (
                # Or the date requested is over 3 days ago
                time_since_given_date > timedelta(days=3)
            ):
                # Then just use stored data
                logger.debug(f"[{self.no}] Found consumptions for: {date.date()}")
                return day_consumption[self.get_unit()]
        return new_consumptions_dataframe(self.get_unit(), "h")[self.get_unit()]

    @requires_init
    def get_daily_consumptions(self, date: datetime) -> pd.Series:
        """Check and return consumptions found for a given month."""
        month_consumption = self.daily_consumptions[
            (self.daily_consumptions.index.month == date.month)
            & (self.daily_consumptions.index.year == date.year)
        ]
        # Check if consumption for this date was already fetched
        if not month_consumption.empty:
            now = datetime.now().astimezone()

            last_checked = month_consumption["last_checked"].min()
            time_since_last_checked = now - last_checked

            time_since_given_date = now - date

            # If not enough time has passed since the last check
            if (time_since_last_checked < REFRESH_INTERVAL) or (
                # Or the date requested is over 1 month + 3 days ago
                time_since_given_date > timedelta(days=34)
            ):
                # Then just use stored data
                logger.debug(f"[{self.no}] Found consumptions for: {date.year}-{date.month}")
                return month_consumption[self.get_unit()]
        return new_consumptions_dataframe(self.get_unit(), "D")[self.get_unit()]

    def calculate_total_consumption(self, consumptions: pd.Series) -> float:
        """Calculate the total consumption from a given pd.Series."""
        if consumptions.empty:
            return 0.0
        total_consumption = round(consumptions.sum(), 3)

        return total_consumption

    def calculate_total_cost(self, consumptions: pd.Series) -> float:
        """Calculate the total cost from a given pd.Series."""
        total_consumption = self.calculate_total_consumption(consumptions)

        tariff = None
        for meter_type, meter_tariff in TARIFFS.items():
            if meter_type.upper() in self.type.upper():
                tariff = meter_tariff
        if tariff is None:
            return 0.0

        total_cost = tariff.calculate_cost(total_consumption)
        return total_cost

    @requires_init
    def get_remaining_unit(self) -> float:
        """Return the last recorded unit for the meter."""
        return self.remaining_unit

    @requires_init
    def get_remaining_credit(self) -> float:
        """Return the last recorded credit for the meter."""
        return self.remaining_credit

    @requires_init
    def get_last_updated(self) -> datetime:
        """Return the last update time for the meter."""
        return self.last_update

    @requires_init
    def is_active(self) -> bool:
        """Return True if the meter status is active."""
        return self.status == "ACTIVE"

    @requires_init
    def get_unit(self) -> str:
        """Return the unit for this meter type."""
        for meter_type, meter_unit in UNITS.items():
            if meter_type.upper() in self.type.upper():
                return meter_unit
        return ""

    @requires_init
    def get_no(self) -> str:
        """Return this meter's meter no."""
        return self.no

    @requires_init
    def get_type(self) -> str:
        """Return this meter's type (Electricity or Water)."""
        return self.type
