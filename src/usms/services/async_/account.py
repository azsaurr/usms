"""Async USMS Account Service."""

from datetime import datetime

import httpx

from usms.core.client import AsyncUSMSClient
from usms.services.account import BaseUSMSAccount
from usms.services.async_.meter import AsyncUSMSMeter
from usms.storage.sqlite import ConsumptionDB
from usms.utils.decorators import requires_init
from usms.utils.logging_config import logger


class AsyncUSMSAccount(BaseUSMSAccount):
    """Async USMS Account Service that inherits BaseUSMSAccount."""

    session: AsyncUSMSClient

    async def initialize(self):
        """Initialize session object, fetch account info and set class attributes."""
        logger.debug(f"[{self.username}] Initializing account {self.username}")

        self.session = await AsyncUSMSClient.create(self.auth)
        self.db = ConsumptionDB(self._db_path) if self._db_path else None

        data = await self.fetch_info()
        await self.from_json(data)

        self._initialized = True
        logger.debug(f"[{self.username}] Initialized account")

    @classmethod
    async def create(cls, username: str, password: str) -> "AsyncUSMSAccount":
        """Initialize and return instance of this class as an object."""
        self = cls(username, password)
        await self.initialize()
        return self

    async def fetch_more_info(self) -> dict:
        """Fetch account information, parse data, initialize class attributes and return as json."""
        logger.debug(f"[{self.username}] Fetching more account details")

        response = await self.session.get("/AccountInfo")
        data = self.parse_more_info(response)

        logger.debug(f"[{self.username}] Fetched more account details")
        return data

    async def fetch_info(self) -> dict:
        """
        Fetch minimal account and meters information.

        Fetch minimal account and meters information, parse data,
        initialize class attributes and return as json.
        """
        logger.debug(f"[{self.username}] Fetching account details")

        response = await self.session.get("/Home")
        data = self.parse_info(response)

        logger.debug(f"[{self.username}] Fetched account details")
        return data

    async def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        super().from_json(data)

        if not hasattr(self, "meters") or self.get_meters() == []:
            self.meters = []
            for meter_data in data.get("meters", []):
                meter = await AsyncUSMSMeter.create(self, meter_data)
                self.meters.append(meter)

    @requires_init
    async def log_out(self) -> bool:
        """Log the user out of the USMS session by clearing session cookies."""
        logger.debug(f"[{self.username}] Logging out {self.username}...")

        await self.session.get("/ResLogin")
        self.session.cookies = {}

        if not await self.is_authenticated():
            logger.debug(f"[{self.username}] Log out successful")
            return True

        logger.error(f"[{self.username}] Log out fail")
        return False

    @requires_init
    async def log_in(self) -> bool:
        """Log in the user."""
        logger.debug(f"[{self.username}] Logging in {self.username}...")

        await self.session.get("/AccountInfo")

        if await self.is_authenticated():
            logger.debug(f"[{self.username}] Log in successful")
            return True

        logger.error(f"[{self.username}] Log in fail")
        return False

    @requires_init
    async def is_authenticated(self) -> bool:
        """
        Check if the current session is authenticated.

        Check if the current session is authenticated
        by sending a request without retrying or triggering auth logic.
        """
        is_authenticated = False
        try:
            response = await self.session.get("/AccountInfo", auth=None)
            is_authenticated = not self.auth.is_expired(response)
        except httpx.HTTPError as error:
            logger.error(f"[{self.username}] Login check failed: {error}")

        if is_authenticated:
            logger.debug(f"[{self.username}] Account is authenticated")
        else:
            logger.debug(f"[{self.username}] Account is NOT authenticated")
        return is_authenticated

    @requires_init
    async def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.debug(f"[{self.username}] Checking for updates")

        try:
            fresh_info = await self.fetch_info()
        except Exception as error:  # noqa: BLE001
            logger.error(f"[{self.username}] Failed to fetch update with error: {error}")
            return False

        self.last_refresh = datetime.now().astimezone()

        for meter in fresh_info.get("meters", []):
            if meter.get("last_update") > self.get_latest_update():
                logger.debug(f"[{self.username}] New updates found")
                await self.from_json(fresh_info)
                return True

        logger.debug(f"[{self.username}] No new updates found")
        return False

    @requires_init
    async def check_update_and_refresh(self) -> bool:
        """Refresh data if an update is due, then return True if update successful."""
        try:
            if self.is_update_due():
                return await self.refresh_data()
        except Exception as error:  # noqa: BLE001
            logger.error(f"[{self.username}] Failed to fetch update with error: {error}")
            return False

        # Update not dued, data not refreshed
        return False
