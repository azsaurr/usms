"""Sync USMS Account Service."""

from datetime import datetime
from pathlib import Path

import httpx

from usms.core.client import USMSClient
from usms.services.account import BaseUSMSAccount
from usms.services.sync.meter import USMSMeter
from usms.utils.decorators import requires_init
from usms.utils.helpers import get_storage
from usms.utils.logging_config import logger


class USMSAccount(BaseUSMSAccount):
    """Sync USMS Account Service that inherits BaseUSMSAccount."""

    session: USMSClient

    def initialize(self):
        """Initialize session object, fetch account info and set class attributes."""
        logger.debug(f"[{self.username}] Initializing account {self.username}")

        self.session = USMSClient.create(self.auth)
        self.storage_manager = get_storage(self._storage_type, self._storage_path)

        data = self.fetch_info()
        self.from_json(data)

        self._initialized = True
        logger.debug(f"[{self.username}] Initialized account")

    @classmethod
    def create(
        cls,
        username: str,
        password: str,
        storage_type: str | None = None,
        storage_path: Path | None = None,
    ) -> "USMSAccount":
        """Initialize and return instance of this class as an object."""
        self = cls(
            username,
            password,
            storage_type,
        )
        self.initialize()
        return self

    def fetch_more_info(self) -> dict:
        """Fetch account information, parse data, initialize class attributes and return as json."""
        logger.debug(f"[{self.username}] Fetching more account details")

        response = self.session.get("/AccountInfo")
        data = self.parse_more_info(response)

        logger.debug(f"[{self.username}] Fetched more account details")
        return data

    def fetch_info(self) -> dict:
        """
        Fetch minimal account and meters information.

        Fetch minimal account and meters information, parse data,
        initialize class attributes and return as json.
        """
        logger.debug(f"[{self.username}] Fetching account details")

        response = self.session.get("/Home")
        data = self.parse_info(response)

        logger.debug(f"[{self.username}] Fetched account details")
        return data

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        super().from_json(data)

        if not hasattr(self, "meters") or self.get_meters() == []:
            self.meters = []
            for meter_data in data.get("meters", []):
                meter = USMSMeter.create(self, meter_data)
                self.meters.append(meter)

    @requires_init
    def log_out(self) -> bool:
        """Log the user out of the USMS session by clearing session cookies."""
        logger.debug(f"[{self.username}] Logging out {self.username}...")

        self.session.get("/ResLogin")
        self.session.cookies = {}

        if not self.is_authenticated():
            logger.debug(f"[{self.username}] Log out successful")
            return True

        logger.error(f"[{self.username}] Log out fail")
        return False

    @requires_init
    def log_in(self) -> bool:
        """Log in the user."""
        logger.debug(f"[{self.username}] Logging in {self.username}...")

        self.session.get("/AccountInfo")

        if self.is_authenticated():
            logger.debug(f"[{self.username}] Log in successful")
            return True

        logger.error(f"[{self.username}] Log in fail")
        return False

    @requires_init
    def is_authenticated(self) -> bool:
        """
        Check if the current session is authenticated.

        Check if the current session is authenticated
        by sending a request without retrying or triggering auth logic.
        """
        is_authenticated = False
        try:
            response = self.session.get("/AccountInfo", auth=None)
            is_authenticated = not self.auth.is_expired(response)
        except httpx.HTTPError as error:
            logger.error(f"[{self.username}] Login check failed: {error}")

        if is_authenticated:
            logger.debug(f"[{self.username}] Account is authenticated")
        else:
            logger.debug(f"[{self.username}] Account is NOT authenticated")
        return is_authenticated

    @requires_init
    def refresh_data(self) -> bool:
        """Fetch new data and update the meter info."""
        logger.debug(f"[{self.username}] Checking for updates")

        try:
            fresh_info = self.fetch_info()
        except Exception as error:  # noqa: BLE001
            logger.error(f"[{self.username}] Failed to fetch update with error: {error}")
            return False

        self.last_refresh = datetime.now().astimezone()

        for meter in fresh_info.get("meters", []):
            if meter.get("last_update") > self.get_latest_update():
                logger.debug(f"[{self.username}] New updates found")
                self.from_json(fresh_info)
                return True

        logger.debug(f"[{self.username}] No new updates found")
        return False

    @requires_init
    def check_update_and_refresh(self) -> bool:
        """Refresh data if an update is due, then return True if update successful."""
        try:
            if self.is_update_due():
                return self.refresh_data()
        except Exception as error:  # noqa: BLE001
            logger.error(f"[{self.username}] Failed to fetch update with error: {error}")
            return False

        # Update not dued, data not refreshed
        return False
