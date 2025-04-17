"""Base USMS Meter Service."""

import base64
from abc import ABC
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Union
from zoneinfo import ZoneInfo

import httpx
import lxml.html
import pandas as pd

from usms.config.constants import BRUNEI_TZ, TARIFFS, UNITS
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
    node_no: str

    last_refresh: datetime
    earliest_consumption_date: datetime
    hourly_consumptions: pd.DataFrame
    daily_consumptions: pd.DataFrame

    update_interval: timedelta
    refresh_interval: timedelta

    def __init__(self, account: Union["USMSAccount", "AsyncUSMSAccount"], node_no: str) -> None:
        """Set initial class variables."""
        self._account = account
        self.session = account.session
        self.node_no = node_no

        self._initialized = False

    def initialize(self):
        """Set initial values for class variables."""
        self.last_refresh = self.last_update
        self.earliest_consumption_date = None

        self.hourly_consumptions = new_consumptions_dataframe(self.get_unit(), "h")
        self.daily_consumptions = new_consumptions_dataframe(self.get_unit(), "D")

        self.update_interval = timedelta(seconds=60 * 60)
        self.refresh_interval = timedelta(seconds=60 * 15)

        self._initialized = True

    def parse_info(self, response: httpx.Response | bytes) -> dict:
        """Parse data from meter info page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        address = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblAddress"]""")
            .text_content()
            .strip()
        )
        kampong = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblKampong"]""")
            .text_content()
            .strip()
        )
        mukim = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMukim"]""").text_content().strip()
        )
        district = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblDistrict"]""")
            .text_content()
            .strip()
        )
        postcode = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblPostcode"]""")
            .text_content()
            .strip()
        )

        no = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterNo"]""")
            .text_content()
            .strip()
        )
        _id = base64.b64encode(no.encode()).decode()

        _type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblMeterType"]""")
            .text_content()
            .strip()
        )
        customer_type = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCustomerType"]""")
            .text_content()
            .strip()
        )

        remaining_unit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblRemainingUnit"]""")
            .text_content()
            .strip()
        )
        remaining_unit = float(remaining_unit.split()[0].replace(",", ""))

        remaining_credit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCurrentBalance"]""")
            .text_content()
            .strip()
        )
        remaining_credit = float(remaining_credit.split("$")[-1].replace(",", ""))

        last_update = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblLastUpdated"]""")
            .text_content()
            .strip()
        )
        date = last_update.split()[0].split("/")
        time = last_update.split()[1].split(":")
        last_update = datetime(
            int(date[2]),
            int(date[1]),
            int(date[0]),
            hour=int(time[0]),
            minute=int(time[1]),
            second=int(time[2]),
            tzinfo=BRUNEI_TZ,
        )

        status = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblStatus"]""")
            .text_content()
            .strip()
        )

        return {
            "address": address,
            "kampong": kampong,
            "mukim": mukim,
            "district": district,
            "postcode": postcode,
            "no": no,
            "id": _id,
            "type": _type,
            "customer_type": customer_type,
            "remaining_unit": remaining_unit,
            "remaining_credit": remaining_credit,
            "last_update": last_update,
            "status": status,
        }

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        self.address = data.get("address", "")
        self.kampong = data.get("kampong", "")
        self.mukim = data.get("mukim", "")
        self.district = data.get("district", "")
        self.postcode = data.get("postcode", "")

        self.no = data.get("no", "")
        self.id = data.get("id", "")

        self.type = data.get("type", "")
        self.customer_type = data.get("customer_type", "")

        self.remaining_unit = data.get("remaining_unit", "")
        self.remaining_credit = data.get("remaining_credit", "")

        self.last_update = data.get("last_update", "")
        self.status = data.get("status", "")

    def _build_info_payload(self) -> dict:
        """Build and return payload for meter info page."""
        payload = {}
        payload["ASPxTreeView1"] = (
            "{&quot;nodesState&quot;:[{&quot;N0_0&quot;:&quot;T&quot;,&quot;N0&quot;:&quot;T&quot;},&quot;"
            + self.node_no
            + "&quot;,{}]}"
        )
        payload["__EVENTARGUMENT"] = f"NCLK|{self.node_no}"
        payload["__EVENTTARGET"] = "ASPxPanel1$ASPxTreeView1"

        return payload

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

        now = sanitize_date(datetime.now(tz=BRUNEI_TZ))
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

    def parse_consumptions_error(self, response: httpx.Response | bytes) -> dict:
        """Parse meter consumptions page for error messages."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        error_message = response_html.find(""".//span[@id="pcErr_lblErrMsg"]""").text_content()
        if error_message:
            return {"error_message": error_message}

        return {"error_message": ""}

    @requires_init
    def get_hourly_consumptions(self, date: datetime) -> pd.Series:
        """Check and return consumptions found for a given day."""
        day_consumption = self.hourly_consumptions[
            self.hourly_consumptions.index.date == date.date()
        ]
        # Check if consumption for this date was already fetched
        if not day_consumption.empty:
            now = datetime.now(tz=BRUNEI_TZ)

            last_checked = day_consumption["last_checked"].min()
            time_since_last_checked = now - last_checked

            time_since_given_date = now - date

            # If not enough time has passed since the last check
            if (time_since_last_checked < self.refresh_interval) or (
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
            now = datetime.now(tz=BRUNEI_TZ)

            last_checked = month_consumption["last_checked"].min()
            time_since_last_checked = now - last_checked

            time_since_given_date = now - date

            # If not enough time has passed since the last check
            if (time_since_last_checked < self.refresh_interval) or (
                # Or the date requested is over 1 month + 3 days ago
                time_since_given_date > timedelta(days=34)
            ):
                # Then just use stored data
                logger.debug(f"[{self.no}] Found consumptions for: {date.year}-{date.month}")
                return month_consumption[self.get_unit()]
        return new_consumptions_dataframe(self.get_unit(), "D")[self.get_unit()]

    def parse_hourly_consumptions(self, response: httpx.Response | bytes) -> dict:
        """Parse data from meter hourly consumptions page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        error_message = self.parse_consumptions_error(response).get("error_message")
        if error_message == "consumption history not found.":
            # this error message is somehow not always true
            # ignore it for now, and check for the table properly instead
            pass
        elif error_message != "":
            logger.error(f"[{self.no}] Error fetching consumptions: {error_message}")

        hourly_consumptions = {}

        table = response_html.find(""".//table[@id="ASPxPageControl1_grid_DXMainTable"]""")
        if table is None:
            return hourly_consumptions

        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            tds = row.findall(".//td")

            hour = int(tds[0].text_content())
            consumption = float(tds[1].text_content())

            hourly_consumptions[hour] = consumption

        return hourly_consumptions

    def parse_daily_consumptions(self, response: httpx.Response | bytes) -> dict:
        """Parse data from meter daily consumptions page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        error_message = self.parse_consumptions_error(response).get("error_message")
        if error_message:
            return new_consumptions_dataframe(self.get_unit(), "D")
            # raise USMSConsumptionHistoryNotFoundError(error_message)  # noqa: ERA001

        daily_consumptions = {}
        table = response_html.find(""".//table[@id="ASPxPageControl1_grid_DXMainTable"]""")
        for row in table.findall(""".//tr[@class="dxgvDataRow"]"""):
            tds = row.findall(".//td")

            day = str(tds[0].text_content())
            consumption = float(tds[1].text_content())

            daily_consumptions[day] = consumption

        return daily_consumptions

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
    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now(tz=BRUNEI_TZ)

        # Interval between checking for new updates
        logger.debug(f"[{self.no}] update_interval: {self.update_interval}")
        logger.debug(f"[{self.no}] refresh_interval: {self.refresh_interval}")

        # Elapsed time since the meter was last updated by USMS
        time_since_last_update = now - self.last_update
        logger.debug(f"[{self.no}] last_update: {self.last_update}")
        logger.debug(f"[{self.no}] time_since_last_update: {time_since_last_update}")

        # Elapsed time since a refresh was last attempted
        time_since_last_refresh = now - self.last_refresh
        logger.debug(f"[{self.no}] last_refresh: {self.last_refresh}")
        logger.debug(f"[{self.no}] time_since_last_refresh: {time_since_last_refresh}")

        # If 60 minutes has passed since meter was last updated by USMS
        if time_since_last_update > self.update_interval:
            logger.debug(f"[{self.no}] time_since_last_update > update_interval")
            # If 15 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > self.refresh_interval:
                logger.debug(f"[{self.no}] time_since_last_refresh > refresh_interval")
                logger.debug(f"[{self.no}] Meter is due for an update")
                return True

            logger.debug(f"[{self.no}] time_since_last_refresh < refresh_interval")
            logger.debug(f"[{self.no}] Meter is NOT due for an update")
            return False

        logger.debug(f"[{self.no}] time_since_last_update < update_interval")
        logger.debug(f"[{self.no}] Meter is NOT due for an update")
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
