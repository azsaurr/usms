"""Base USMS Meter Service."""

from abc import ABC
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from usms.config.constants import BRUNEI_TZ, REFRESH_INTERVAL, TARIFFS
from usms.models.meter import USMSMeter as USMSMeterModel
from usms.parsers.error_message_parser import ErrorMessageParser
from usms.parsers.meter_consumptions_parser import MeterConsumptionsParser
from usms.parsers.meter_payment_info_parser import MeterPaymentInfoParser
from usms.utils.decorators import requires_init
from usms.utils.helpers import new_consumptions, sanitize_date
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.core.client import USMSClient
    from usms.services.account import BaseUSMSAccount


class BaseUSMSMeter(ABC, USMSMeterModel):
    """Base USMS Meter Service to be inherited."""

    _account: "BaseUSMSAccount"
    session: "USMSClient"

    earliest_consumption_date: datetime

    # Consumptions are {timestamp: consumption}, with the time each entry was last
    # fetched held alongside so the refresh check does not need a parallel column.
    hourly_consumptions: dict[datetime, float]
    daily_consumptions: dict[datetime, float]
    hourly_last_checked: dict[datetime, datetime]
    daily_last_checked: dict[datetime, datetime]

    def __init__(self, account: "BaseUSMSAccount") -> None:
        """Set initial class variables."""
        self._account = account
        self.session = account.session
        self.storage_manager = account.storage_manager

        self._initialized = False

    def initialize(self) -> None:
        """Set initial values for class variables."""
        self.earliest_consumption_date = None

        self._initialized = True

        self.hourly_consumptions = new_consumptions(self.unit, "h")
        self.daily_consumptions = new_consumptions(self.unit, "D")
        self.hourly_last_checked = {}
        self.daily_last_checked = {}

    def _build_hourly_consumptions_payload(self, date: datetime) -> dict[str, str]:
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

    def _build_daily_consumptions_payload(self, date: datetime) -> dict[str, str]:
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

    def _parse_hourly_consumptions_response(
        self,
        response_content: bytes,
        date: datetime,
    ) -> dict[datetime, float]:
        """
        Parse an hourly UsageHistory response into a consumptions mapping.

        Shared verbatim by the sync and async services, which differ only in how the
        response body is read. Hours are reported 1-24, keyed to the start of the hour.
        """
        self._log_consumptions_error(response_content)

        return {
            date + timedelta(hours=int(hour) - 1): float(consumption)
            for hour, consumption in MeterConsumptionsParser.parse(response_content).items()
        }

    def _parse_daily_consumptions_response(
        self,
        response_content: bytes,
        date: datetime,
    ) -> dict[datetime, float]:
        """
        Parse a daily UsageHistory response into a consumptions mapping.

        Shared verbatim by the sync and async services. Days are reported zero-based
        within the month, and are keyed to midnight Brunei time.
        """
        self._log_consumptions_error(response_content)

        return {
            datetime(date.year, date.month, int(day) + 1, tzinfo=BRUNEI_TZ): float(consumption)
            for day, consumption in MeterConsumptionsParser.parse(response_content).items()
        }

    @property
    def _payment_info_path(self) -> str:
        """Return the path of this meter's Top Up page, which carries the debt details."""
        return f"/Payment/WebForm2?p={self.id}&s=h"

    def _parse_payment_info_response(self, response_content: bytes) -> dict[str, str]:
        """Parse a Top Up page response and apply it to this meter."""
        data = MeterPaymentInfoParser.parse(response_content)
        self.update_from_payment_json(data)

        logger.debug("[%s] Fetched payment info, debt owing: %s", self.no, self.total_debt_owing)
        return data

    def _log_consumptions_error(self, response_content: bytes) -> None:
        """Log any error carried by a UsageHistory response."""
        error_message = ErrorMessageParser.parse(response_content).get("error_message")

        if error_message == "consumption history not found.":
            # this error message is somehow not always true
            # ignore it for now, and check for the table properly instead
            return

        if error_message:
            logger.error("[%s] Error fetching consumptions: %s", self.no, error_message)

    def _is_stored_data_usable(
        self,
        stored_consumptions: dict[datetime, float],
        last_checked_map: dict[datetime, datetime],
        date: datetime,
        settled_after: timedelta,
    ) -> bool:
        """
        Return True if stored consumptions for a date can be used without refetching.

        Stored data is reused either when it was checked recently, or when the date is
        old enough that USMS will not revise it any further.
        """
        last_checked = min(
            (
                last_checked_map[timestamp]
                for timestamp in stored_consumptions
                if timestamp in last_checked_map
            ),
            default=None,
        )
        if last_checked is None:
            return False

        now = datetime.now().astimezone()
        return (now - last_checked < REFRESH_INTERVAL) or (now - date > settled_after)

    @requires_init
    def get_hourly_consumptions(self, date: datetime) -> dict[datetime, float]:
        """Check and return consumptions found for a given day."""
        day_consumption = {
            timestamp: consumption
            for timestamp, consumption in self.hourly_consumptions.items()
            if timestamp.date() == date.date()
        }

        # Check if consumption for this date was already fetched, and is still usable
        if day_consumption and self._is_stored_data_usable(
            day_consumption,
            self.hourly_last_checked,
            date,
            timedelta(days=3),
        ):
            logger.debug("[%s] Found consumptions for: %s", self.no, date.date())
            return day_consumption

        return new_consumptions(self.unit, "h")

    @requires_init
    def get_daily_consumptions(self, date: datetime) -> dict[datetime, float]:
        """Check and return consumptions found for a given month."""
        month_consumption = {
            timestamp: consumption
            for timestamp, consumption in self.daily_consumptions.items()
            if (timestamp.month, timestamp.year) == (date.month, date.year)
        }

        # Check if consumption for this date was already fetched, and is still usable
        if month_consumption and self._is_stored_data_usable(
            month_consumption,
            self.daily_last_checked,
            date,
            timedelta(days=34),
        ):
            logger.debug("[%s] Found consumptions for: %s-%s", self.no, date.year, date.month)
            return month_consumption

        return new_consumptions(self.unit, "D")

    def _earliest_daily_consumption_date(self) -> datetime:
        """
        Return the earliest date present in the daily consumptions.

        Used for meters that expose no hourly report (water): there is nothing to
        probe for, so the earliest date we can claim is the earliest daily reading
        already held. Nothing is cached when no data is held yet, so a later call
        can still resolve it once daily consumptions have been fetched.
        """
        if not self.daily_consumptions:
            return datetime.now().astimezone()

        self.earliest_consumption_date = min(self.daily_consumptions)
        return self.earliest_consumption_date

    def calculate_total_consumption(self, consumptions: dict[datetime, float]) -> float:
        """Calculate the total consumption from the given consumptions."""
        if not consumptions:
            return 0.0

        return round(sum(consumptions.values()), 3)

    def calculate_total_cost(self, consumptions: dict[datetime, float]) -> float:
        """Calculate the total cost from the given consumptions."""
        total_consumption = self.calculate_total_consumption(consumptions)

        tariff = None
        for meter_type, meter_tariff in TARIFFS.items():
            if meter_type.upper() in self.type.upper():
                tariff = meter_tariff
        if tariff is None:
            return 0.0

        total_cost = tariff.calculate_cost(total_consumption)
        return total_cost
