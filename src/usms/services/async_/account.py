"""Async USMS Account Service."""

import httpx

from usms.core.client import AsyncUSMSClient
from usms.services.account import BaseUSMSAccount
from usms.services.async_.meter import AsyncUSMSMeter
from usms.utils.decorators import requires_init
from usms.utils.logging_config import logger


class AsyncUSMSAccount(BaseUSMSAccount):
    """Async USMS Account Service that inherits BaseUSMSAccount."""

    session: AsyncUSMSClient

    async def initialize(self):
        """Initialize session object, fetch account info and set class attributes."""
        logger.debug(f"[{self.username}] Initializing account {self.username}")
        self.session = await AsyncUSMSClient.create(self.auth)
        await self.fetch_info()

        self._initialized = True
        logger.debug(f"[{self.username}] Initialized account")

    @classmethod
    async def create(cls, username: str, password: str) -> "AsyncUSMSAccount":
        """Initialize and return instance of this class as an object."""
        self = cls(username, password)
        await self.initialize()
        await self.initialize_meters()
        return self

    @requires_init
    async def initialize_meters(self):
        """Initialize all USMSMeters under this account."""
        for meter in self.meters:
            await meter.initialize()

    async def fetch_info(self) -> dict:
        """Fetch account information, parse data, initialize class attributes and return as json."""
        logger.debug(f"[{self.username}] Fetching account details")

        response = await self.session.get("/AccountInfo")

        data = self.parse_info(response)
        await self.from_json(data)

        logger.debug(f"[{self.username}] Fetched account details")
        return data

    async def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        self.reg_no = data.get("reg_no", "")
        self.name = data.get("name", "")
        self.contact_no = data.get("contact_no", "")
        self.email = data.get("email", "")

        self.meters = []
        for meter_node_no in data.get("meters", []):
            self.meters.append(AsyncUSMSMeter(self, meter_node_no))

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
