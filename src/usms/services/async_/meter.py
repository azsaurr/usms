"""Async USMS Meter Service."""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from usms.parsers.error_message_parser import ErrorMessageParser
from usms.parsers.meter_consumptions_parser import MeterConsumptionsParser
from usms.services.meter import BaseUSMSMeter
from usms.utils.decorators import requires_init
from usms.utils.helpers import (
    consumptions_storage_to_dataframe,
    dataframe_diff,
    new_consumptions_dataframe,
    sanitize_date,
)
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.services.async_.account import AsyncUSMSAccount


class AsyncUSMSMeter(BaseUSMSMeter):
    """Async USMS Meter Service that inherits BaseUSMSMeter."""

    async def initialize(self, data: dict[str, str]) -> None:
        """Fetch meter info and then set initial class attributes."""
        logger.debug(f"[{self._account.reg_no}] Initializing meter")
        self.update_from_json(data)
        super().initialize()

        if self.storage_manager is not None:
            consumptions = await asyncio.to_thread(
                self.storage_manager.get_all_consumptions,
                self.no,
            )
            self.hourly_consumptions = consumptions_storage_to_dataframe(consumptions)

            self.hourly_consumptions.rename(
                columns={"consumption": self.unit},
                inplace=True,
            )

        logger.debug(f"[{self._account.reg_no}] Initialized meter")

    @classmethod
    async def create(cls, account: "AsyncUSMSAccount", data: dict[str, str]) -> "AsyncUSMSMeter":
        """Initialize and return instance of this class as an object."""
        self = cls(account)
        await self.initialize(data)
        return self

    @requires_init
    async def fetch_hourly_consumptions(
        self,
        date: datetime,
        *,
        force_refresh: bool = False,
    ) -> pd.Series:
        """Fetch hourly consumptions for a given date and return as pd.Series."""
        date = sanitize_date(date)

        if not force_refresh:
            day_consumption = self.get_hourly_consumptions(date)
            if not day_consumption.empty:
                return day_consumption

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.date()}")
        # build payload and perform requests
        payload = self._build_hourly_consumptions_payload(date)
        await self.session.get(f"/Report/UsageHistory?p={self.id}")
        await self.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        payload = self._build_hourly_consumptions_payload(date)
        response = await self.session.post(
            f"/Report/UsageHistory?p={self.id}",
            data=payload,
        )
        response_content = await response.aread()

        error_message = ErrorMessageParser.parse(response_content).get("error_message")
        if error_message == "consumption history not found.":
            # this error message is somehow not always true
            # ignore it for now, and check for the table properly instead
            pass
        elif error_message is not None and error_message != "":
            logger.error(f"[{self.no}] Error fetching consumptions: {error_message}")

        hourly_consumptions = MeterConsumptionsParser.parse(response_content)

        # convert dict to pd.DataFrame
        hourly_consumptions = pd.DataFrame.from_dict(
            hourly_consumptions,
            dtype=float,
            orient="index",
            columns=[self.unit],
        )

        if hourly_consumptions.empty:
            logger.warning(f"[{self.no}] No consumptions data for : {date.date()}")
            return hourly_consumptions[self.unit]

        hourly_consumptions.index = pd.to_datetime(
            [date + timedelta(hours=int(hour) - 1) for hour in hourly_consumptions.index]
        )
        hourly_consumptions = hourly_consumptions.asfreq("h")
        hourly_consumptions["last_checked"] = datetime.now().astimezone()

        self.hourly_consumptions = hourly_consumptions.combine_first(self.hourly_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.date()}")
        return hourly_consumptions[self.unit]

    @requires_init
    async def fetch_daily_consumptions(
        self,
        date: datetime,
        *,
        force_refresh: bool = False,
    ) -> pd.Series:
        """Fetch daily consumptions for a given date and return as pd.Series."""
        date = sanitize_date(date)

        if not force_refresh:
            month_consumption = self.get_daily_consumptions(date)
            if not month_consumption.empty:
                return month_consumption

        logger.debug(f"[{self.no}] Fetching consumptions for: {date.year}-{date.month}")
        # build payload and perform requests
        payload = self._build_daily_consumptions_payload(date)

        await self.session.get(f"/Report/UsageHistory?p={self.id}")
        await self.session.post(f"/Report/UsageHistory?p={self.id}")
        await self.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = await self.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response_content = await response.aread()

        error_message = ErrorMessageParser.parse(response_content).get("error_message")
        if error_message:
            daily_consumptions = new_consumptions_dataframe(self.unit, "D")
        else:
            daily_consumptions = MeterConsumptionsParser.parse(response_content)

        # convert dict to pd.DataFrame
        daily_consumptions = pd.DataFrame.from_dict(
            daily_consumptions,
            dtype=float,
            orient="index",
            columns=[self.unit],
        )
        daily_consumptions.index = pd.to_datetime(
            [f"{date.year}-{date.month:02d}-{int(day) + 1}" for day in daily_consumptions.index]
        )
        daily_consumptions = daily_consumptions.asfreq("D")
        daily_consumptions["last_checked"] = datetime.now().astimezone()

        if daily_consumptions.empty:
            logger.warning(f"[{self.no}] No consumptions data for : {date.year}-{date.month}")
            return daily_consumptions[self.unit]

        self.daily_consumptions = daily_consumptions.combine_first(self.daily_consumptions)

        logger.debug(f"[{self.no}] Fetched consumptions for: {date.year}-{date.month}")
        return daily_consumptions[self.unit]

    @requires_init
    async def get_previous_n_month_consumptions(self, n: int = 0) -> pd.Series:
        """
        Return the consumptions for previous n month.

        e.g.
        n=0 : data for this month only
        n=1 : data for previous month only
        n=2 : data for previous 2 months only
        """
        date = datetime.now().astimezone()
        for _ in range(n):
            date = date.replace(day=1)
            date = date - timedelta(days=1)
        return await self.fetch_daily_consumptions(date)

    @requires_init
    async def get_last_n_days_hourly_consumptions(self, n: int = 0) -> pd.Series:
        """
        Return the hourly unit consumptions for the last n days accumulatively.

        e.g.
        n=0 : data for today
        n=1 : data from yesterday until today
        n=2 : data from 2 days ago until today
        """
        last_n_days_hourly_consumptions = new_consumptions_dataframe(
            self.unit,
            "h",
        )[self.unit]

        upper_date = datetime.now().astimezone()
        lower_date = upper_date - timedelta(days=n)
        for i in range(n + 1):
            date = lower_date + timedelta(days=i)
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

            if not hourly_consumptions.empty:
                last_n_days_hourly_consumptions = hourly_consumptions.combine_first(
                    last_n_days_hourly_consumptions
                )

            if n > 3:  # noqa: PLR2004
                progress = round((i + 1) / (n + 1) * 100, 1)
                logger.info(
                    f"[{self.no}] Getting last {n} days hourly consumptions progress: {(i + 1)} out of {(n + 1)}, {progress}%"
                )

        return last_n_days_hourly_consumptions

    @requires_init
    async def get_all_hourly_consumptions(self) -> pd.Series:
        """Get the hourly unit consumptions for all days and months."""
        logger.debug(f"[{self.no}] Getting all hourly consumptions")

        upper_date = datetime.now().astimezone()
        lower_date = await self.find_earliest_consumption_date()
        range_date = (upper_date - lower_date).days + 1
        for i in range(range_date):
            date = lower_date + timedelta(days=i)
            await self.fetch_hourly_consumptions(date)
            progress = round((i + 1) / range_date * 100, 1)
            logger.info(
                f"[{self.no}] Getting all hourly consumptions progress: {(i + 1)} out of {range_date}, {progress}%"
            )

        return self.hourly_consumptions[self.unit]

    @requires_init
    async def find_earliest_consumption_date(self) -> datetime:
        """Determine the earliest date for which hourly consumption data is available."""
        if self.earliest_consumption_date is not None:
            return self.earliest_consumption_date

        now = datetime.now().astimezone()
        if self.hourly_consumptions.empty:
            for i in range(7):
                date = now - timedelta(days=i)
                hourly_consumptions = await self.fetch_hourly_consumptions(date)
                if not hourly_consumptions.empty:
                    break
        else:
            date = self.hourly_consumptions.index.min()
        logger.info(f"[{self.no}] Finding earliest consumption date, starting from: {date.date()}")

        # Exponential backoff to find a missing date
        step = 1
        while True:
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

            if not hourly_consumptions.empty:
                step *= 2  # Exponentially increase step
                logger.info(f"[{self.no}] Stepping {step} days from {date}")
                date -= timedelta(days=step)
            elif step == 1:
                if self.hourly_consumptions.empty:
                    logger.error(f"[{self.no}] Cannot determine earliest available date")
                    return now
                # Already at base step, this is the earliest available data
                date += timedelta(days=step)
                self.earliest_consumption_date = date
                logger.info(f"[{self.no}] Found earliest consumption date: {date}")
                return date
            else:
                # Went too far — reverse the last large step and reset step to 1
                date += timedelta(days=step)
                logger.debug(f"[{self.no}] Stepped too far, going back to: {date}")
                step /= 4  # Half the last step

    @requires_init
    async def store_consumptions(self, consumptions: pd.DataFrame) -> None:
        """Insert consumptions in the given dataframe to the database."""
        new_statistics_df = dataframe_diff(self.hourly_consumptions, consumptions)

        for row in new_statistics_df.itertuples(index=True, name="Row"):
            await asyncio.to_thread(
                self.storage_manager.insert_or_replace,
                meter_no=self.no,
                timestamp=int(row.Index.timestamp()),
                consumption=getattr(row, self.unit),
                last_checked=int(row.last_checked.timestamp()),
            )
