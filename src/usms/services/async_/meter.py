"""
USMS Meter Module.

This module defines the USMSMeter class,
which represents a smart meter in the USMS system.
It provides methods to retrieve meter details,
check for updates and retrieve consumption histories.
"""

from datetime import datetime, timedelta

import pandas as pd

from usms.config.constants import BRUNEI_TZ
from usms.services.meter import BaseUSMSMeter
from usms.utils.helpers import sanitize_date
from usms.utils.logging_config import logger


class AsyncUSMSMeter(BaseUSMSMeter):
    """
    Represents a USMS meter.

    Represents a USMS meter, allowing access to meter details
    and consumption histories.
    """

    async def initialize(self):
        """
        Initialize a USMSMeter instance.

        Fetch a USMSMeter instance, through the node number of its associated account.
        """
        logger.debug(f"[{self._account.username}] Initializing meter {self.node_no}")
        await self.fetch_info()
        super().initialize()
        logger.debug(f"[{self._account.username}] Initialized meter {self.node_no}")

    async def fetch_info(self) -> dict:
        """Fetch meter information, parse data, initialize class attributes and return as json."""
        payload = self._build_info_payload()
        await self.session.get("/AccountInfo")
        response = await self.session.post("/AccountInfo", data=payload)

        data = self.parse_info(response)
        self.from_json(data)

        logger.debug(f"[{self.no}] Fetched {self.type} meter {self.no}")
        return data

    async def fetch_hourly_consumptions(self, date: datetime) -> pd.Series:
        """Fetch hourly consumptions for a given date and return as pd.Series."""
        date = sanitize_date(date)

        day_consumption = self.get_hourly_consumptions(date)
        if not day_consumption.empty:
            return day_consumption

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.date()}")
        # build payload and perform requests
        payload = self._build_hourly_consumptions_payload(date)
        await self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        payload = self._build_hourly_consumptions_payload(date)
        response = await self._account.session.post(
            f"/Report/UsageHistory?p={self.id}",
            data=payload,
        )

        hourly_consumptions = self.parse_hourly_consumptions(response)

        # convert dict to pd.DataFrame
        hourly_consumptions = pd.DataFrame.from_dict(
            hourly_consumptions,
            dtype=float,
            orient="index",
            columns=[self.get_unit()],
        )
        hourly_consumptions.index = pd.to_datetime(
            [date + timedelta(hours=hour) for hour in hourly_consumptions.index]
        )
        hourly_consumptions = hourly_consumptions.asfreq("h")
        hourly_consumptions["last_checked"] = datetime.now(tz=BRUNEI_TZ)

        if hourly_consumptions.empty:
            logger.debug(f"[{self.no}] No consumptions data for : {date.date()}")
            return hourly_consumptions[self.get_unit()]

        self.hourly_consumptions = hourly_consumptions.combine_first(self.hourly_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.date()}")
        return hourly_consumptions[self.get_unit()]

    async def fetch_daily_consumptions(self, date: datetime) -> pd.Series:
        """Fetch daily consumptions for a given date and return as pd.Series."""
        date = sanitize_date(date)

        month_consumption = self.get_daily_consumptions(date)
        if not month_consumption.empty:
            return month_consumption

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.year}-{date.month}")
        # build payload and perform requests
        payload = self._build_daily_consumptions_payload(date)

        await self._account.session.get(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}")
        await self._account.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = await self._account.session.post(
            f"/Report/UsageHistory?p={self.id}", data=payload
        )

        daily_consumptions = self.parse_daily_consumptions(response)

        # convert dict to pd.DataFrame
        daily_consumptions = pd.DataFrame.from_dict(
            daily_consumptions,
            dtype=float,
            orient="index",
            columns=[self.get_unit()],
        )
        daily_consumptions.index = pd.to_datetime(daily_consumptions.index, format="%d/%m/%Y")
        daily_consumptions = daily_consumptions.asfreq("D")
        daily_consumptions["last_checked"] = datetime.now(tz=BRUNEI_TZ)

        if daily_consumptions.empty:
            logger.debug(f"[{self.no}] No consumptions data for : {date.year}-{date.month}")
            return daily_consumptions[self.get_unit()]

        self.daily_consumptions = daily_consumptions.combine_first(self.daily_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.year}-{date.month}")
        return daily_consumptions[self.get_unit()]

    async def get_previous_n_month_consumptions(self, n=0) -> pd.Series:
        """
        Return the consumptions for previous n month.

        e.g.
        n=0 : data for this month only
        n=1 : data for previous month only
        n=2 : data for previous 2 months only
        """
        date = datetime.now(tz=BRUNEI_TZ)
        for _ in range(n):
            date = date.replace(day=1)
            date = date - timedelta(days=1)
        return await self.fetch_daily_consumptions(date)

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
        for i in range(n + 1):
            date = lower_date + timedelta(days=i)
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

            if not hourly_consumptions.empty:
                last_n_days_hourly_consumptions = hourly_consumptions.combine_first(
                    last_n_days_hourly_consumptions
                )

        return last_n_days_hourly_consumptions

    async def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.info(f"[{self.no}] Checking for updates")

        try:
            # Initialize a temporary meter to fetch fresh details in one call
            temp_meter = AsyncUSMSMeter(self._account, self.node_no)
            temp_info = await temp_meter.fetch_info()
        except Exception as error:  # noqa: BLE001
            logger.warning(f"[{self.no}] Failed to fetch update with error: {error}")
            return False

        self.last_refresh = datetime.now(tz=BRUNEI_TZ)

        if temp_info.get("last_update") > self.last_update:
            logger.info(f"[{self.no}] New updates found")
            self.from_json(temp_info)
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

    async def get_all_hourly_consumptions(self) -> pd.Series:
        """Get the hourly unit consumptions for all days and months."""
        logger.debug(f"[{self.no}] Getting all hourly consumptions")

        upper_date = datetime.now(tz=BRUNEI_TZ)
        lower_date = await self.find_earliest_consumption_date()
        range_date = (upper_date - lower_date).days + 1
        for i in range(range_date):
            date = lower_date + timedelta(days=i)
            await self.fetch_hourly_consumptions(date)
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
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

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
