"""
USMS Meter Module.

This module defines the USMSMeter class,
which represents a smart meter in the USMS system.
It provides methods to retrieve meter details,
check for updates and retrieve consumption histories.
"""

import base64
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import lxml.html

from usms.config.constants import BRUNEI_TZ, TARIFFS, UNITS
from usms.exceptions.errors import (
    USMSConsumptionHistoryNotFoundError,
    USMSFutureDateError,
)
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.models.account import USMSAccount


class USMSMeter:
    """
    Represents a USMS meter.

    Represents a USMS meter, allowing access to meter details
    and consumption histories.
    """

    """USMS Meter class attributes."""
    _account: "USMSAccount"
    _node_no: str

    address: str
    kampong: str
    mukim: str
    district: str
    postcode: str

    no: str
    id: str  # base64 encoded meter no

    type: str
    customer_type: str
    remaining_unit: float
    remaining_credit: float

    last_update: datetime

    status: str

    def __init__(self, account: "USMSAccount", node_no: str) -> None:
        """
        Initialize a USMSMeter instance.

        Fetch a USMSMeter instance, through the node number of its associated account.
        """
        self._account = account
        self._node_no = node_no

        self.fetch_details()
        self.last_refresh = self.last_update

    def fetch_details(self) -> None:
        """
        Fetch and set meter details.

        Fetch and set meter details including address, number and id
        type, remaining unit and credit, and last update timestamp.
        """
        """Retrieves initial USMS Meter attributes."""

        # build payload
        payload = {}
        payload["ASPxTreeView1"] = (
            "{&quot;nodesState&quot;:[{&quot;N0_0&quot;:&quot;T&quot;,&quot;N0&quot;:&quot;T&quot;},&quot;"
            + self._node_no
            + "&quot;,{}]}"
        )
        payload["__EVENTARGUMENT"] = f"NCLK|{self._node_no}"
        payload["__EVENTTARGET"] = "ASPxPanel1$ASPxTreeView1"

        self._account.session.get("/AccountInfo")
        response = self._account.session.post("/AccountInfo", data=payload)
        response_html = lxml.html.fromstring(response.content)

        self.address = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblAddress"]""")
            .text_content()
            .strip()
        )
        self.kampong = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblKampong"]""")
            .text_content()
            .strip()
        )
        self.mukim = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMukim"]""").text_content().strip()
        )
        self.district = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblDistrict"]""")
            .text_content()
            .strip()
        )
        self.postcode = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblPostcode"]""")
            .text_content()
            .strip()
        )

        self.no = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterNo"]""")
            .text_content()
            .strip()
        )
        self.id = base64.b64encode(self.no.encode()).decode()

        self.type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterType"]""")
            .text_content()
            .strip()
        )
        self.customer_type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCustomerType"]""")
            .text_content()
            .strip()
        )

        self.remaining_unit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblRemainingUnit"]""")
            .text_content()
            .strip()
        )
        self.remaining_unit = float(self.remaining_unit.split()[0].replace(",", ""))

        self.remaining_credit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCurrentBalance"]""")
            .text_content()
            .strip()
        )
        self.remaining_credit = float(self.remaining_credit.split("$")[-1].replace(",", ""))

        self.last_update = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblLastUpdated"]""")
            .text_content()
            .strip()
        )
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

        self.status = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblStatus"]""")
            .text_content()
            .strip()
        )

        logger.debug(f"[{self.no}] Fetched {self.type} meter {self.no}")

    def get_hourly_consumptions(self, date: datetime) -> dict:
        """Return the hourly unit consumptions for a given day."""
        # make sure given date has timezone info
        if not date.tzinfo:
            logger.debug(f"[{self.no}] Given date has no timezone, assuming {BRUNEI_TZ}")
            date = date.replace(tzinfo=BRUNEI_TZ)

        now = datetime.now(tz=BRUNEI_TZ)

        # make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch = date.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        # build payload
        payload = {}
        payload["cboType_VI"] = "3"
        payload["cboType"] = "Hourly (Max 1 day)"

        self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)

        payload = {"btnRefresh": ["Search", ""]}
        payload["cboDateFrom"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        payload["cboDateTo$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        response = self._account.session.post(
            f"/Report/UsageHistory?p={self.id}",
            data=payload,
        )
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(""".//span[@id="pcErr_lblErrMsg"]""").text_content()
        if error_message == "consumption history not found.":
            logger.error(f"[{self.no}] Error: {error_message}")
            return {}
        if error_message:
            raise USMSConsumptionHistoryNotFoundError(error_message)

        table = response_html.find(""".//table[@id="ASPxPageControl1_grid_DXMainTable"]""")

        hourly_consumptions = {}
        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            tds = row.findall(".//td")

            hour = int(tds[0].text_content())

            if hour < 24:  # noqa: PLR2004
                hour = datetime(
                    date.year,
                    date.month,
                    date.day,
                    hour,
                    0,
                    0,
                    tzinfo=BRUNEI_TZ,
                )
            else:
                hour = datetime(
                    date.year,
                    date.month,
                    date.day,
                    23,
                    0,
                    0,
                    tzinfo=BRUNEI_TZ,
                )
                hour = hour + timedelta(hours=1)

            consumption = float(tds[1].text_content())

            hourly_consumptions[hour] = consumption

        logger.debug(f"[{self.no}] Retrieved consumption for: {date.date()}")
        return hourly_consumptions

    def get_daily_consumptions(self, date: datetime) -> dict:
        """Return the daily unit consumptions for a given month."""
        # make sure given date has timezone info
        if not date.tzinfo:
            logger.debug(f"[{self.no}] Given date has no timezone, assuming {BRUNEI_TZ}")
            date = date.replace(tzinfo=BRUNEI_TZ)

        now = datetime.now(tz=BRUNEI_TZ)

        # make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

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

        # check if given month is still ongoing
        if date.year == now.year and date.month == now.month:
            # then get consumption up until yesterday only
            date = date - timedelta(days=1)
        else:
            # otherwise get until the last day of the month
            next_month = date.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            date = date.replace(day=last_day.day)

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch_to = date.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        # build payload
        payload = {}
        payload["cboType_VI"] = "1"
        payload["cboType"] = "Daily (Max 1 month)"
        payload["btnRefresh"] = "Search"
        payload["cboDateFrom"] = f"01/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch_from}&quot;" + "}"
        payload["cboDateTo$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch_to}&quot;" + "}"

        self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        self._account.session.post(f"/Report/UsageHistory?p={self.id}")
        self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(""".//span[@id="pcErr_lblErrMsg"]""").text_content()
        if error_message == "consumption history not found.":
            logger.error(f"[{self.no}] Error: {error_message}")
            return {}
        if error_message:
            raise USMSConsumptionHistoryNotFoundError(error_message)

        table = response_html.find(""".//table[@id="ASPxPageControl1_grid_DXMainTable"]""")

        daily_consumptions = {}
        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            tds = row.findall(".//td")

            day = int(tds[0].text_content().split("/")[0])
            day = datetime(
                date.year,
                date.month,
                day,
                0,
                0,
                0,
                tzinfo=BRUNEI_TZ,
            )

            consumption = float(tds[1].text_content())

            daily_consumptions[day] = consumption

        logger.debug(f"[{self.no}] Retrieved consumption for: {date.year}-{date.month}")
        return daily_consumptions

    def get_total_day_consumption(self, date: datetime) -> float:
        """Return the total unit consumption for a given day."""
        hourly_consumptions = self.get_hourly_consumptions(date)

        total_consumption = 0
        for consumption in hourly_consumptions.values():
            total_consumption += consumption

        total_consumption = round(total_consumption, 3)

        logger.debug(f"[{self.no}] Consumption for {date.date()}: {total_consumption}")
        return total_consumption

    def get_total_month_consumption(self, date: datetime) -> float:
        """Return the total unit consumption for a given month."""
        daily_consumptions = self.get_daily_consumptions(date)

        total_consumption = 0
        for consumption in daily_consumptions.values():
            total_consumption += consumption

        total_consumption = round(total_consumption, 3)

        logger.debug(f"[{self.no}] Consumption for {date.year}-{date.month}: {total_consumption}")
        return total_consumption

    def get_hourly_consumption(self, date: datetime) -> float | None:
        """Return the unit consumption for a given hour."""
        date = datetime(
            date.year,
            date.month,
            date.day,
            date.hour,
            0,
            0,
            tzinfo=date.tzinfo,
        )

        hourly_consumptions = self.get_hourly_consumptions(date)
        consumption = hourly_consumptions.get(date, None)

        if consumption is None:
            logger.warning(f"[{self.no}] No consumption recorded yet for {date}")

        return consumption

    def get_last_consumption(self) -> float | None:
        """Return the unit consumption for the last hour."""
        now = datetime.now(tz=BRUNEI_TZ)
        consumption = self.get_hourly_consumption(now)

        logger.debug(f"[{self.no}] Consumption for {now}: {consumption} {self.get_unit()}")
        return consumption

    def get_total_month_cost(self, date: datetime) -> float:
        """Return the total cost for a given month."""
        total_cost = 0.0
        for meter_type, tariff in TARIFFS.items():
            if meter_type.upper() in self.type.upper():
                total_consumption = self.get_total_month_consumption(date)

                total_cost = tariff.calculate_cost(total_consumption)
                total_cost = round(total_cost, 2)

        logger.debug(f"[{self.no}] Cost for {date.year}-{date.month}: ${total_cost}")
        return total_cost

    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now(tz=BRUNEI_TZ)

        # Interval between checking for new updates
        update_interval = timedelta(seconds=3600)  # 60 minutes
        logger.debug(f"[{self.no}] update_interval: {update_interval}")

        # Elapsed time since the meter was last updated by USMS
        time_since_last_update = now - self.last_update
        logger.debug(f"[{self.no}] last_update: {self.last_update}")
        logger.debug(f"[{self.no}] time_since_last_update: {time_since_last_update}")

        # Elapsed time since a refresh was last attempted
        time_since_last_refresh = now - self.last_refresh
        logger.debug(f"[{self.no}] last_refresh: {self.last_refresh}")
        logger.debug(f"[{self.no}] time_since_last_refresh: {time_since_last_refresh}")

        # If 60 minutes has passed since meter was last updated by USMS
        if time_since_last_update > update_interval:
            logger.debug(f"[{self.no}] time_since_last_update > update_interval")
            # If 60 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > update_interval:
                logger.debug(f"[{self.no}] time_since_last_refresh > update_interval")
                logger.info(f"[{self.no}] Meter is due for an update")
                return True

            logger.debug(f"[{self.no}] time_since_last_refresh < update_interval")
            logger.info(f"[{self.no}] Meter is NOT due for an update")
            return False

        logger.debug(f"[{self.no}] time_since_last_update < update_interval")
        logger.info(f"[{self.no}] Meter is NOT due for an update")
        return False

    def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.info(f"[{self.no}] Checking for updates")

        try:
            # Initialize a temporary meter to fetch fresh details in one call
            temp_meter = USMSMeter(self._account, self._node_no)
        except Exception as error:  # noqa: BLE001
            logger.warning(f"[{self.no}] Failed to fetch update with error: {error}")
            return False

        self.last_refresh = datetime.now(tz=BRUNEI_TZ)

        if temp_meter.last_update > self.last_update:
            logger.info(f"[{self.no}] New updates found")
            self.last_update = temp_meter.last_update
            self.remaining_credit = temp_meter.remaining_credit
            self.remaining_unit = temp_meter.remaining_unit

            return True

        logger.info(f"[{self.no}] No new updates found")
        return False

    def check_update_and_refresh(self) -> bool:
        """Refresh data if an update is due, then return True if update successful."""
        try:
            if self.is_update_due():
                return self.refresh_data()
        except Exception as error:  # noqa: BLE001
            logger.warning(f"[{self.no}] Failed to fetch update with error: {error}")
            return False

        # Update not dued, data not refreshed
        return False

    def get_remaining_unit(self) -> float:
        """Return the last recorded unit for the meter."""
        return self.remaining_unit

    def get_remaining_credit(self) -> float:
        """Return the last recorded credit for the meter."""
        return self.remaining_credit

    def get_last_updated(self) -> datetime:
        """Return the last update time for the meter."""
        return self.last_update

    def is_active(self) -> bool:
        """Return True if the meter status is active."""
        return self.status == "ACTIVE"

    def get_unit(self) -> str:
        """Return the unit for this meter type."""
        for meter_type, meter_unit in UNITS.items():
            if meter_type.upper() in self.type.upper():
                return meter_unit
        return ""

    def get_no(self) -> str:
        """Return this meter's meter no."""
        return self.no

    def get_type(self) -> str:
        """Return this meter's type (Electricity or Water)."""
        return self.type
