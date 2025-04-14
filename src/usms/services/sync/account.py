"""
USMS Account Module.

This module defines the USMSAccount class,
which represents a user account in the USMS system.
It provides methods to retrieve account details,
manage associated meters and handle user sessions.
"""

import httpx

from usms.core.client import USMSClient
from usms.services.account import BaseUSMSAccount
from usms.services.sync.meter import USMSMeter
from usms.utils.logging_config import logger


class USMSAccount(BaseUSMSAccount):
    """
    Represents a USMS account.

    Represents a USMS account, allowing access to account details
    and associated meters.
    """

    session: USMSClient

    def initialize(self):
        """Initialize a USMSAccount instance."""
        logger.debug(f"[{self.username}] Initializing account {self.username}")
        self.session = USMSClient.create(self.auth)
        self.fetch_info()
        logger.debug(f"[{self.username}] Initialized account")

    def initialize_meters(self):
        """Initialize all USMSMeters under this account."""
        for meter in self.meters:
            meter.initialize()

    def fetch_info(self) -> dict:
        """Fetch account information, parse data, initialize class attributes and return as json."""
        logger.debug(f"[{self.username}] Fetching account details")

        response = self.session.get("/AccountInfo")

        data = self.parse_info(response)
        self.from_json(data)

        logger.debug(f"[{self.username}] Fetched account details")
        return data

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        self.reg_no = data.get("reg_no", "")
        self.name = data.get("name", "")
        self.contact_no = data.get("contact_no", "")
        self.email = data.get("email", "")

        self.meters = []
        for meter_node_no in data.get("meters", []):
            self.meters.append(USMSMeter(self, meter_node_no))

    def log_out(self) -> bool:
        """Log the user out of the USMS session by clearing session cookies."""
        logger.debug(f"[{self.username}] Logging out {self.username}...")
        self.session.get("/ResLogin")
        self.session.cookies = {}

        if not self.is_authenticated():
            logger.debug(f"[{self.username}] Logged out")
            return True

        logger.debug(f"[{self.username}] Log out fail")
        return False

    def log_in(self) -> bool:
        """Log in the user."""
        logger.debug(f"[{self.username}] Logging in {self.username}...")

        self.session.get("/AccountInfo")

        if self.is_authenticated():
            logger.debug(f"[{self.username}] Logged in")
            return True

        logger.debug(f"[{self.username}] Log in fail")
        return False

    def is_authenticated(self) -> bool:
        """
        Check if the current session is authenticated.

        Check if the current session is authenticated
        by sending a request without retrying or triggering auth logic.
        """
        logger.debug(f"[{self.username}] Checking if authenticated")
        is_authenticated = False
        try:
            # Temporarily disable the custom Auth
            usms_auth = self.session.auth
            self.session.auth = None

            # Build and send a raw request without auth logic
            request = self.session.build_request("GET", f"{self.session.BASE_URL}/AccountInfo")
            response = self.session.send(request, stream=False)

            # Now check manually using custom Auth logic
            is_authenticated = not usms_auth.is_expired(response)

            if is_authenticated:
                logger.debug(f"[{self.username}] Account is authenticated")
            else:
                logger.debug(f"[{self.username}] Account is NOT authenticated")
        except httpx.HTTPError as error:
            logger.warning(f"[{self.username}] Login check failed: {error}")
        finally:
            # Restore the custom Auth back
            self.session.auth = usms_auth

        return is_authenticated
