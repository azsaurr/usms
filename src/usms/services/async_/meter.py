"""Async USMS Meter Service."""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from usms.services.meter import BaseUSMSMeter
from usms.utils.decorators import requires_init
from usms.utils.helpers import (
    consumptions_diff,
    consumptions_from_storage,
    merge_consumptions,
    new_consumptions,
    sanitize_date,
)
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.services.async_.account import AsyncUSMSAccount


class AsyncUSMSMeter(BaseUSMSMeter):
    """Async USMS Meter Service that inherits BaseUSMSMeter."""

    async def initialize(self, data: dict[str, str]) -> None:
        """Fetch meter info and then set initial class attributes."""
        logger.debug("[%s] Initializing meter", self._account.reg_no)
        self.update_from_json(data)
        super().initialize()

        if self.storage_manager is not None:
            consumptions = await asyncio.to_thread(
                self.storage_manager.get_all_consumptions,
                self.no,
            )
            self.hourly_consumptions, self.hourly_last_checked = consumptions_from_storage(
                consumptions
            )

        logger.debug("[%s] Initialized meter", self._account.reg_no)

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
    ) -> dict[datetime, float]:
        """Fetch hourly consumptions for a given date."""
        date = sanitize_date(date)

        if not self.supports_hourly_consumptions:
            logger.debug("[%s] Skipping hourly fetch, unsupported for this meter", self.no)
            return new_consumptions(self.unit, "h")

        if not force_refresh:
            day_consumption = self.get_hourly_consumptions(date)
            if day_consumption:
                return day_consumption

        logger.debug("[%s] Fetching consumptions for: %s", self.no, date.date())
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

        hourly_consumptions = self._parse_hourly_consumptions_response(response_content, date)
        if not hourly_consumptions:
            logger.warning("[%s] No consumptions data for : %s", self.no, date.date())
            return hourly_consumptions

        last_checked = datetime.now().astimezone()

        if self.storage_manager is not None:
            await self.store_consumptions(hourly_consumptions, last_checked)

        self.hourly_consumptions = merge_consumptions(hourly_consumptions, self.hourly_consumptions)
        self.hourly_last_checked.update(dict.fromkeys(hourly_consumptions, last_checked))

        logger.debug("[%s] Fetched consumptions for: %s", self.no, date.date())
        return hourly_consumptions

    @requires_init
    async def fetch_daily_consumptions(
        self,
        date: datetime,
        *,
        force_refresh: bool = False,
    ) -> dict[datetime, float]:
        """Fetch daily consumptions for a given date."""
        date = sanitize_date(date)

        if not force_refresh:
            month_consumption = self.get_daily_consumptions(date)
            if month_consumption:
                return month_consumption

        logger.debug("[%s] Fetching consumptions for: %s-%s", self.no, date.year, date.month)
        # build payload and perform requests
        payload = self._build_daily_consumptions_payload(date)

        await self.session.get(f"/Report/UsageHistory?p={self.id}")
        await self.session.post(f"/Report/UsageHistory?p={self.id}")
        await self.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response = await self.session.post(f"/Report/UsageHistory?p={self.id}", data=payload)
        response_content = await response.aread()

        daily_consumptions = self._parse_daily_consumptions_response(response_content, date)
        if not daily_consumptions:
            logger.warning("[%s] No consumptions data for : %s-%s", self.no, date.year, date.month)
            return daily_consumptions

        last_checked = datetime.now().astimezone()

        self.daily_consumptions = merge_consumptions(daily_consumptions, self.daily_consumptions)
        self.daily_last_checked.update(dict.fromkeys(daily_consumptions, last_checked))

        logger.debug("[%s] Fetched consumptions for: %s-%s", self.no, date.year, date.month)
        return daily_consumptions

    @requires_init
    async def fetch_payment_info(self) -> dict[str, str]:
        """
        Fetch this meter's debt and customer details from its Top Up page.

        These are not exposed anywhere else in USMS, and are read-only: the page's
        payment form redirects to the bank, so `topup_url` is the way to act on it.
        """
        logger.debug("[%s] Fetching payment info", self.no)
        response = await self.session.get(self._payment_info_path)
        return self._parse_payment_info_response(await response.aread())

    @requires_init
    async def get_previous_n_month_consumptions(self, n: int = 0) -> dict[datetime, float]:
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
    async def get_last_n_days_hourly_consumptions(self, n: int = 0) -> dict[datetime, float]:
        """
        Return the hourly unit consumptions for the last n days accumulatively.

        e.g.
        n=0 : data for today
        n=1 : data from yesterday until today
        n=2 : data from 2 days ago until today
        """
        last_n_days_hourly_consumptions = new_consumptions(self.unit, "h")

        if not self.supports_hourly_consumptions:
            logger.debug("[%s] Skipping hourly fetch, unsupported for this meter", self.no)
            return last_n_days_hourly_consumptions

        upper_date = datetime.now().astimezone()
        lower_date = upper_date - timedelta(days=n)
        for i in range(n + 1):
            date = lower_date + timedelta(days=i)
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

            if hourly_consumptions:
                last_n_days_hourly_consumptions = merge_consumptions(
                    hourly_consumptions,
                    last_n_days_hourly_consumptions,
                )

            if n > 3:  # noqa: PLR2004
                progress = round((i + 1) / (n + 1) * 100, 1)
                logger.info(
                    "[%s] Getting last %s days hourly consumptions progress: %s out of %s, %s%%",
                    self.no,
                    n,
                    i + 1,
                    n + 1,
                    progress,
                )

        return last_n_days_hourly_consumptions

    @requires_init
    async def get_all_hourly_consumptions(self) -> dict[datetime, float]:
        """Get the hourly unit consumptions for all days and months."""
        logger.debug("[%s] Getting all hourly consumptions", self.no)

        if not self.supports_hourly_consumptions:
            logger.debug("[%s] Skipping hourly fetch, unsupported for this meter", self.no)
            return self.hourly_consumptions

        upper_date = datetime.now().astimezone()
        lower_date = await self.find_earliest_consumption_date()
        range_date = (upper_date - lower_date).days + 1
        for i in range(range_date):
            date = lower_date + timedelta(days=i)
            await self.fetch_hourly_consumptions(date)
            progress = round((i + 1) / range_date * 100, 1)
            logger.info(
                "[%s] Getting all hourly consumptions progress: %s out of %s, %s%%",
                self.no,
                i + 1,
                range_date,
                progress,
            )

        return self.hourly_consumptions

    @requires_init
    async def find_earliest_consumption_date(self) -> datetime:
        """Determine the earliest date for which hourly consumption data is available."""
        if self.earliest_consumption_date is not None:
            return self.earliest_consumption_date

        # No hourly report exists to probe for water, so there is nothing to search.
        if not self.supports_hourly_consumptions:
            return self._earliest_daily_consumption_date()

        now = datetime.now().astimezone()
        if not self.hourly_consumptions:
            for i in range(7):
                date = now - timedelta(days=i)
                hourly_consumptions = await self.fetch_hourly_consumptions(date)
                if hourly_consumptions:
                    break
        else:
            date = min(self.hourly_consumptions)
        logger.info(
            "[%s] Finding earliest consumption date, starting from: %s", self.no, date.date()
        )

        # Exponential backoff to find a missing date
        step = 1
        while True:
            hourly_consumptions = await self.fetch_hourly_consumptions(date)

            if hourly_consumptions:
                step *= 2  # Exponentially increase step
                date -= timedelta(days=step)
                logger.info("[%s] Stepping %s days from %s", self.no, step, date)
            elif step == 1:
                if not self.hourly_consumptions:
                    logger.error("[%s] Cannot determine earliest available date", self.no)
                    return now
                # Already at base step, this is the earliest available data
                date += timedelta(days=step)
                self.earliest_consumption_date = date
                logger.info("[%s] Found earliest consumption date: %s", self.no, date)
                return date
            else:
                # Went too far — reverse the last large step and reset step to 1
                date += timedelta(days=step)
                logger.debug("[%s] Stepped too far, going back to: %s", self.no, date)
                step /= 4  # Half the last step

    @requires_init
    async def store_consumptions(
        self,
        consumptions: dict[datetime, float],
        last_checked: datetime,
    ) -> None:
        """Insert the given consumptions into the database."""
        new_consumptions_map = consumptions_diff(self.hourly_consumptions, consumptions)

        for timestamp, consumption in new_consumptions_map.items():
            await asyncio.to_thread(
                self.storage_manager.insert_or_replace,
                meter_no=self.no,
                timestamp=int(timestamp.timestamp()),
                consumption=consumption,
                last_checked=int(last_checked.timestamp()),
            )
