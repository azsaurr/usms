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
import pandas as pd

from usms.config.constants import BRUNEI_TZ, TARIFFS, UNITS
from usms.exceptions.errors import (
    USMSConsumptionHistoryNotFoundError,
    USMSFutureDateError,
)
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.models.async_account import AsyncUSMSAccount


class AsyncUSMSMeter:
    """
    Represents a USMS meter.

    Represents a USMS meter, allowing access to meter details
    and consumption histories.
    """

    """USMS Meter class attributes."""
    _account: "AsyncUSMSAccount"
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

    last_refresh: datetime
    earliest_consumption_date: datetime
    hourly_consumptions: pd.DataFrame
    daily_consumptions: pd.DataFrame

    update_interval: timedelta

    def __init__(self, account: "AsyncUSMSAccount", node_no: str) -> None:
        """Initialize a USMSMeter instance."""
        self._account = account
        self._node_no = node_no

        self.last_refresh = None

    async def initialize(self):
        """
        Initialize a USMSMeter instance.

        Fetch a USMSMeter instance, through the node number of its associated account.
        """
        logger.debug(f"[{self._account.username}] Initializing meter {self._node_no}")

        await self.fetch_details()
        self.last_refresh = self.last_update
        self.earliest_consumption_date = None

        self.hourly_consumptions = pd.DataFrame(
            dtype=float,
            columns=[self.get_unit(), "last_checked"],
            index=pd.DatetimeIndex(
                [],
                tz=BRUNEI_TZ,
                freq="h",
            ),
        )
        self.hourly_consumptions["last_checked"] = pd.to_datetime(
            self.hourly_consumptions["last_checked"]
        ).dt.tz_localize(BRUNEI_TZ)

        self.daily_consumptions = pd.DataFrame(
            dtype=float,
            columns=[self.get_unit(), "last_checked"],
            index=pd.DatetimeIndex(
                [],
                tz=BRUNEI_TZ,
                freq="h",
            ),
        )
        self.daily_consumptions["last_checked"] = pd.to_datetime(
            self.daily_consumptions["last_checked"]
        ).dt.tz_localize(BRUNEI_TZ)

        self.update_interval = timedelta(seconds=3600)

        logger.debug(f"[{self._account.username}] Initialized meter {self._node_no}")

    async def fetch_details(self) -> None:
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

        await self._account.session.get("/AccountInfo")
        response = await self._account.session.post("/AccountInfo", data=payload)
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

        remaining_unit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblRemainingUnit"]""")
            .text_content()
            .strip()
        )
        self.remaining_unit = float(remaining_unit.split()[0].replace(",", ""))

        remaining_credit = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblCurrentBalance"]""")
            .text_content()
            .strip()
        )
        self.remaining_credit = float(remaining_credit.split("$")[-1].replace(",", ""))

        last_update = (
            response_html.find(""".//span[@id="ASPxFormLayout1_lblLastUpdated"]""")
            .text_content()
            .strip()
        )
        date = last_update.split()[0].split("/")
        time = last_update.split()[1].split(":")
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

    async def get_hourly_consumptions(self, date: datetime) -> pd.Series:  # noqa: C901, PLR0915
        """Return the hourly unit consumptions for a given day."""
        # Make sure given date has timezone info
        if not date.tzinfo:
            logger.debug(f"[{self.no}] Given date has no timezone, assuming {BRUNEI_TZ}")
            date = date.replace(tzinfo=BRUNEI_TZ)

        now = datetime.now(tz=BRUNEI_TZ)

        # Make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

        # Check if consumption for this date was already fetched
        day_consumption = self.hourly_consumptions[
            self.hourly_consumptions.index.date == date.date()
        ]
        if not day_consumption.empty:
            no_of_hours = 24
            if self.hourly_consumptions.index.min().date() == date.date():
                # This check is because the earliest date is always missing 00:00:00
                no_of_hours = 23

            # Makes sure that the data is complete for the day
            if (day_consumption.shape[0] == no_of_hours) or (
                # If it is incomplete, and it is today, that means it might have been updated
                (date.date() == now.date())
                # Also check if not enough time has passed since last check, then use stored data
                and ((now - self.hourly_consumptions["last_checked"].min()) < self.update_interval)
            ):
                logger.debug(f"[{self.no}] Found consumptions for: {date.date()}")
                return day_consumption[self.get_unit()]

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.date()}")

        yyyy = date.year
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        epoch = date.replace(tzinfo=ZoneInfo("UTC")).timestamp() * 1000

        # build payload
        payload = {}
        payload["cboType_VI"] = "3"
        payload["cboType"] = "Hourly (Max 1 day)"

        await self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)

        payload = {"btnRefresh": ["Search", ""]}
        payload["cboDateFrom"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateTo"] = f"{dd}/{mm}/{yyyy}"
        payload["cboDateFrom$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        payload["cboDateTo$State"] = "{" + f"&quot;rawValue&quot;:&quot;{epoch}&quot;" + "}"
        response = await self._account.session.post(
            f"/Report/UsageHistory?p={self.id}",
            data=payload,
        )
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(""".//span[@id="pcErr_lblErrMsg"]""").text_content()
        if error_message == "consumption history not found.":
            logger.error(f"[{self.no}] Error: {error_message} for: {date.date()}")
            # just return empty Series
            return pd.Series(
                dtype=float,
                index=pd.DatetimeIndex([], tz=BRUNEI_TZ, freq="h"),
                name=self.get_unit(),
            )
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

        hourly_consumptions = pd.DataFrame.from_dict(
            hourly_consumptions,
            dtype=float,
            orient="index",
            columns=[self.get_unit()],
        )
        hourly_consumptions.index = pd.to_datetime(hourly_consumptions.index)
        hourly_consumptions = hourly_consumptions.asfreq("h")
        hourly_consumptions["last_checked"] = now

        if hourly_consumptions.empty:
            logger.debug(f"[{self.no}] No consumptions data for : {date.date()}")
            return hourly_consumptions[self.get_unit()]

        self.hourly_consumptions = hourly_consumptions.combine_first(self.hourly_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.date()}")
        return hourly_consumptions[self.get_unit()]

    async def get_daily_consumptions(self, date: datetime) -> pd.Series:  # noqa: PLR0915
        """Return the daily unit consumptions for a given month."""
        # Make sure given date has timezone info
        if not date.tzinfo:
            logger.debug(f"[{self.no}] Given date has no timezone, assuming {BRUNEI_TZ}")
            date = date.replace(tzinfo=BRUNEI_TZ)

        now = datetime.now(tz=BRUNEI_TZ)

        # Make sure the given day is not in the future
        if date > now:
            raise USMSFutureDateError(date)

        # Check if consumption for this month was already fetched
        month_consumption = self.daily_consumptions[
            (self.daily_consumptions.index.month == date.month)
            & (self.daily_consumptions.index.year == date.year)
        ]
        if not month_consumption.empty:  # noqa: SIM102
            if (
                # Makes sure that the data is complete for the month
                (month_consumption.shape[0] == pd.Timestamp(date).days_in_month)
                # Or if its the earliest month recorded (possible missing data)
                or (
                    self.hourly_consumptions.index.min().year == date.year
                    and self.hourly_consumptions.index.min().month == date.month
                )
                # If this month and enough time has passed since last check, then use stored data
                or (
                    (date.year == now.year and date.month == now.month)
                    and (
                        (now - self.daily_consumptions["last_checked"].min()) < self.update_interval
                    )
                )
            ):
                logger.debug(f"[{self.no}] Found consumptions for: {date.year}-{date.month}")
                return month_consumption[self.get_unit()]

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

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.year}-{date.month}")

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

        await self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = await self._account.session.post(
            f"/Report/UsageHistory?p={self.id}", data=payload
        )
        response_html = lxml.html.fromstring(response.content)

        error_message = response_html.find(""".//span[@id="pcErr_lblErrMsg"]""").text_content()
        if error_message == "consumption history not found.":
            logger.error(f"[{self.no}] Error: {error_message} for: {date.year}-{date.month}")
            # just return empty series
            return pd.Series(
                dtype=float,
                index=pd.DatetimeIndex([], tz=BRUNEI_TZ, freq="h"),
                name=self.get_unit(),
            )
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

        daily_consumptions = pd.DataFrame.from_dict(
            daily_consumptions,
            dtype=float,
            orient="index",
            columns=[self.get_unit()],
        )
        daily_consumptions.index = pd.to_datetime(daily_consumptions.index)
        daily_consumptions = daily_consumptions.asfreq("D")
        daily_consumptions["last_checked"] = now

        if daily_consumptions.empty:
            logger.debug(f"[{self.no}] No consumptions data for : {date.year}-{date.month}")
            return daily_consumptions[self.get_unit()]

        self.daily_consumptions = daily_consumptions.combine_first(self.daily_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.year}-{date.month}")
        return daily_consumptions[self.get_unit()]

    async def get_total_day_consumption(self, date: datetime) -> float:
        """Return the total unit consumption for a given day."""
        hourly_consumptions = await self.get_hourly_consumptions(date)

        if hourly_consumptions.empty:
            logger.debug(f"[{self.no}] No consumption calculated for {date.date()}")
            return 0

        total_consumption = round(hourly_consumptions.sum(), 3)

        logger.debug(
            f"[{self.no}] Total consumption for {date.date()}: {total_consumption} {self.get_unit()}"
        )
        return total_consumption

    async def get_total_month_consumption(self, date: datetime) -> float:
        """Return the total unit consumption for a given month."""
        daily_consumptions = await self.get_daily_consumptions(date)

        if daily_consumptions.empty:
            logger.debug(f"[{self.no}] No consumption calculated for {date.year}-{date.month}")
            return 0
        total_consumption = round(daily_consumptions.sum(), 3)

        logger.debug(
            f"[{self.no}] Total consumption for {date.year}-{date.month}: {total_consumption} {self.get_unit()}"
        )
        return total_consumption

    async def get_hourly_consumption(self, date: datetime) -> float | None:
        """Return the unit consumption for a single given hour."""
        date = datetime(
            date.year,
            date.month,
            date.day,
            date.hour,
            0,
            0,
            tzinfo=date.tzinfo,
        )

        hourly_consumptions = await self.get_hourly_consumptions(date)

        if hourly_consumptions.empty:
            logger.warning(f"[{self.no}] No consumption recorded yet for {date}")
            return None

        consumption = hourly_consumptions.squeeze()
        logger.debug(f"[{self.no}] Consumption for {date}: {consumption} {self.get_unit()}")
        return consumption

    async def get_last_consumption(self) -> float | None:
        """Return the unit consumption for the last hour."""
        now = datetime.now(tz=BRUNEI_TZ)

        return await self.get_hourly_consumption(now)

    async def get_total_month_cost(self, date: datetime) -> float | None:
        """Return the total cost for a given month."""
        total_consumption = await self.get_total_month_consumption(date)

        tariff = None
        for meter_type, meter_tariff in TARIFFS.items():
            if meter_type.upper() in self.type.upper():
                tariff = meter_tariff

        if tariff is None:
            return None

        total_cost = tariff.calculate_cost(total_consumption)
        logger.debug(f"[{self.no}] Cost for {date.year}-{date.month}: ${total_cost}")
        return total_cost

    async def get_previous_n_month_total_consumption(self, n=0) -> float:
        """
        Return the total unit consumption for previous n month.

        e.g.
        n=0 : data for this month only
        n=1 : data for previous month only
        n=2 : data for previous 2 months only
        """
        date = datetime.now(tz=BRUNEI_TZ)
        for _ in range(n):
            date = date.replace(day=1)
            date = date - timedelta(days=1)
        return await self.get_total_month_consumption(date)

    async def get_previous_n_month_total_cost(self, n=0) -> float:
        """
        Return the total cost for previous n month.

        e.g.
        n=0 : data for this month only
        n=1 : data for previous month only
        n=2 : data for previous 2 months only
        """
        date = datetime.now(tz=BRUNEI_TZ)
        for _ in range(n):
            date = date.replace(day=1)
            date = date - timedelta(days=1)
        return await self.get_total_month_cost(date)

    async def get_last_n_days_hourly_consumptions(self, n=0) -> pd.Series:
        """
        Return the hourly unit consumptions for the last n days accumulatively.

        e.g.
        n=0 : data for today
        n=1 : data from yesterday until today
        n=2 : data from 2 days ago until today
        """
        last_n_days_hourly_consumptions = pd.Series(
            dtype=float,
            index=pd.DatetimeIndex([], tz=BRUNEI_TZ, freq="h"),
            name=self.get_unit(),
        )

        upper_date = datetime.now(tz=BRUNEI_TZ)
        lower_date = upper_date - timedelta(days=n)
        range_date = (upper_date - lower_date).days + 1
        for i in range(range_date):
            date = lower_date + timedelta(days=i)
            hourly_consumptions = await self.get_hourly_consumptions(date)

            if not hourly_consumptions.empty:
                last_n_days_hourly_consumptions = hourly_consumptions.combine_first(
                    last_n_days_hourly_consumptions
                )

        return last_n_days_hourly_consumptions

    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now(tz=BRUNEI_TZ)

        # Interval between checking for new updates
        logger.debug(f"[{self.no}] update_interval: {self.update_interval}")

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
            # If 60 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > self.update_interval:
                logger.debug(f"[{self.no}] time_since_last_refresh > update_interval")
                logger.info(f"[{self.no}] Meter is due for an update")
                return True

            logger.debug(f"[{self.no}] time_since_last_refresh < update_interval")
            logger.info(f"[{self.no}] Meter is NOT due for an update")
            return False

        logger.debug(f"[{self.no}] time_since_last_update < update_interval")
        logger.info(f"[{self.no}] Meter is NOT due for an update")
        return False

    async def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.info(f"[{self.no}] Checking for updates")

        try:
            # Initialize a temporary meter to fetch fresh details in one call
            temp_meter = AsyncUSMSMeter(self._account, self._node_no)
            await temp_meter.initialize()
        except Exception as error:  # noqa: BLE001
            logger.warning(f"[{self.no}] Failed to fetch update with error: {error}")
            return False

        self.last_refresh = datetime.now(tz=BRUNEI_TZ)

        if temp_meter.last_update > self.last_update:
            logger.info(f"[{self.no}] New updates found")
            self.last_update = temp_meter.get_last_updated()
            self.remaining_credit = temp_meter.get_remaining_credit()
            self.remaining_unit = temp_meter.get_remaining_unit()

            return True

        logger.info(f"[{self.no}] No new updates found")
        return False

    async def check_update_and_refresh(self) -> bool:
        """Refresh data if an update is due, then return True if update successful."""
        try:
            if self.is_update_due():
                return await self.refresh_data()
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
            if meter_type.upper() in self.get_type().upper():
                return meter_unit
        return ""

    def get_no(self) -> str:
        """Return this meter's meter no."""
        return self.no

    def get_type(self) -> str:
        """Return this meter's type (Electricity or Water)."""
        return self.type

    async def get_all_hourly_consumptions(self) -> pd.Series:
        """Get the hourly unit consumptions for all days and months."""
        logger.debug(f"[{self.no}] Getting all hourly consumptions")

        upper_date = datetime.now(tz=BRUNEI_TZ)
        lower_date = await self.find_earliest_consumption_date()
        range_date = (upper_date - lower_date).days + 1
        for i in range(range_date):
            date = lower_date + timedelta(days=i)
            await self.get_hourly_consumptions(date)
            logger.debug(
                f"[{self.no}] Getting all hourly consumptions progress: {i} out of {range_date}, {i / range_date * 100}%"
            )

        return self.hourly_consumptions

    async def find_earliest_consumption_date(self) -> datetime:
        """Determine the earliest date for which hourly consumption data is available."""
        if self.earliest_consumption_date is not None:
            return self.earliest_consumption_date

        if self.hourly_consumptions.empty:
            now = datetime.now(tz=BRUNEI_TZ)
            date = datetime(
                now.year,
                now.month,
                now.day,
                0,
                0,
                0,
                tzinfo=BRUNEI_TZ,
            )
        else:
            date = self.hourly_consumptions.index.min()
        logger.debug(f"[{self.no}] Finding earliest consumption date, starting from: {date.date()}")

        # Exponential backoff to find a missing date
        step = 1
        while True:
            hourly_consumptions = await self.get_hourly_consumptions(date)

            if not hourly_consumptions.empty:
                step *= 2  # Exponentially increase step
                date -= timedelta(days=step)
                logger.debug(f"[{self.no}] Stepping {step} days from {date}")
            elif step == 1:
                # Already at base step, this is the earliest available data
                date += timedelta(days=step)
                self.earliest_consumption_date = date
                logger.debug(f"[{self.no}] Found earliest consumption date: {date}")
                return date
            else:
                # Went too far — reverse the last large step and reset step to 1
                date += timedelta(days=step)
                logger.debug(f"[{self.no}] Stepped too far, going back to: {date}")
                step /= 4  # Half the last step
