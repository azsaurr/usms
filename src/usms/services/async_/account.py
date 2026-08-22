"""Async USMS Account Service."""

from datetime import datetime
from typing import TYPE_CHECKING

from usms.config.constants import BRUNEI_TZ
from usms.core.client import USMSClient
from usms.parsers.account_info_parser import AccountInfoParser
from usms.services.account import BaseUSMSAccount
from usms.services.async_.meter import AsyncUSMSMeter
from usms.storage.base_storage import BaseUSMSStorage
from usms.utils.decorators import requires_init
from usms.utils.helpers import parse_datetime
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.storage.base_storage import BaseUSMSStorage


class AsyncUSMSAccount(BaseUSMSAccount):
    """Async USMS Account Service that inherits BaseUSMSAccount."""

    async def initialize(self):
        """Initialize session object, fetch account info and set class attributes."""
        logger.debug("[%s] Initializing account %s", self.reg_no, self.reg_no)

        data = await self.fetch_info()
        await self.update_from_json(data)

        self._initialized = True
        logger.debug("[%s] Initialized account", self.reg_no)

    @classmethod
    async def create(
        cls,
        session: USMSClient,
        storage_manager: "BaseUSMSStorage | None" = None,
    ) -> "AsyncUSMSAccount":
        """Initialize and return instance of this class as an object."""
        self = cls(
            session,
            storage_manager,
        )
        await self.initialize()
        return self

    async def fetch_info(self) -> dict[str, str]:
        """
        Fetch minimal account and meters information.

        Fetch minimal account and meters information, parse data,
        initialize class attributes and return as json.
        """
        logger.debug("[%s] Fetching account details", self.reg_no)

        response = await self.session.get("/Home")
        response_content = await response.aread()
        data = AccountInfoParser.parse(response_content)

        logger.debug("[%s] Fetched account details", self.reg_no)
        return data

    async def update_from_json(self, data: dict[str, str]) -> None:
        """Initialize base attributes from a json/dict data."""
        super().update_from_json(data)

        if not hasattr(self, "meters") or self.meters == []:
            self.meters = []
            for meter_data in data.get("meters", []):
                meter = await AsyncUSMSMeter.create(self, meter_data)
                self.meters.append(meter)

    @requires_init
    async def log_out(self) -> bool:
        """Log the user out of the USMS session by clearing session cookies."""
        logger.debug("[%s] Logging out %s...", self.reg_no, self.reg_no)

        await self.session.get("/ResLogin")
        self.session.cookies = {}

        if not await self.is_authenticated():
            logger.debug("[%s] Log out successful", self.reg_no)
            return True

        logger.error("[%s] Log out fail", self.reg_no)
        return False

    @requires_init
    async def log_in(self) -> bool:
        """Log in the user."""
        logger.debug("[%s] Logging in %s...", self.reg_no, self.reg_no)

        await self.session.get("/AccountInfo")

        if await self.is_authenticated():
            logger.debug("[%s] Log in successful", self.reg_no)
            return True

        logger.error("[%s] Log in fail", self.reg_no)
        return False

    @requires_init
    async def is_authenticated(self) -> bool:
        """
        Check if the current session is authenticated.

        Check if the current session is authenticated
        by sending a request without retrying or triggering auth logic.
        """
        response = await self.session.get("/AccountInfo", auth=None)
        is_authenticated = not self.auth.is_expired(response)

        if is_authenticated:
            logger.debug("[%s] Account is authenticated", self.reg_no)
        else:
            logger.debug("[%s] Account is NOT authenticated", self.reg_no)
        return is_authenticated

    @requires_init
    async def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.debug("[%s] Checking for updates", self.reg_no)

        try:
            fresh_info = await self.fetch_info()
        except Exception as error:  # noqa: BLE001
            logger.error("[%s] Failed to fetch update with error: %s", self.reg_no, error)
            return False

        self.last_refresh = datetime.now().astimezone()

        for meter in fresh_info.get("meters", []):
            last_update = parse_datetime(meter.get("last_update")).astimezone(BRUNEI_TZ)
            if last_update > self.get_latest_update():
                logger.debug("[%s] New updates found", self.reg_no)
                await self.update_from_json(fresh_info)
                return True

        logger.debug("[%s] No new updates found", self.reg_no)
        return False

    @requires_init
    async def check_update_and_refresh(self) -> bool:
        """Refresh data if an update is due, then return True if update successful."""
        try:
            if self.is_update_due():
                return await self.refresh_data()
        except Exception as error:  # noqa: BLE001
            logger.error("[%s] Failed to fetch update with error: %s", self.reg_no, error)
            return False

        # Update not dued, data not refreshed
        return False

    async def aclose(self) -> None:
        """Close the underlying HTTP client, if this account created it."""
        await self.session.aclose()

    async def __aenter__(self) -> "AsyncUSMSAccount":  # noqa: PYI034  # typing.Self needs 3.11, this package supports 3.10
        """Return the account for use as an async context manager."""
        return self

    async def __aexit__(self, *exc_details: object) -> None:
        """Close the underlying HTTP client on exit."""
        await self.aclose()
