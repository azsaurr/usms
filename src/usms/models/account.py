"""
USMS Account Module.

This module defines the USMSAccount class,
which represents a user account in the USMS system.
It provides methods to retrieve account details,
manage associated meters and handle user sessions.
"""

from datetime import datetime

import httpx
import lxml.html

from usms.config.constants import BRUNEI_TZ
from usms.core.client import USMSClient
from usms.exceptions.errors import USMSMeterNumberError
from usms.models.meter import USMSMeter
from usms.utils.logging_config import logger


class USMSAccount:
    """
    Represents a USMS account.

    Represents a USMS account, allowing access to account details
    and associated meters.
    """

    session: None

    """USMS Account class attributes."""
    reg_no: str
    name: str
    contact_no: str
    email: str
    meters: list

    def __init__(self, username: str, password: str) -> None:
        """
        Initialize a USMSAccount instance.

        Initialize a USMSAccount instance by authenticating the user
        and retrieving account details.
        """
        self.username = username

        self.session = USMSClient(username, password)

        logger.debug(f"[{self.username}] Initializing account {self.username}")
        self.fetch_details()
        logger.debug(f"[{self.username}] Initialized account")

    def fetch_details(self) -> None:
        """
        Fetch and set account details.

        Fetch and set account details including registration number,
        name, contact number, email, and associated meters.
        """
        logger.debug(f"[{self.username}] Fetching account details")

        response = self.session.get("/AccountInfo")
        response_html = lxml.html.fromstring(response.content)

        self.reg_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblIDNumber"]"""
        ).text_content()
        self.name = response_html.find(""".//span[@id="ASPxFormLayout1_lblName"]""").text_content()
        self.contact_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblContactNo"]"""
        ).text_content()
        self.email = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblEmail"]"""
        ).text_content()

        # Get all meters associated with this account
        self.meters = []
        root = response_html.find(""".//div[@id="ASPxPanel1_ASPxTreeView1_CD"]""")  # Nx_y_z
        for x, lvl1 in enumerate(root.findall("./ul/li")):
            for y, lvl2 in enumerate(lvl1.findall("./ul/li")):
                for z, _ in enumerate(lvl2.findall("./ul/li")):
                    meter = USMSMeter(self, f"N{x}_{y}_{z}")
                    self.meters.append(meter)

        logger.debug(f"[{self.username}] Fetched account details: {self.name}")

    def get_meter(self, meter_no: str | int) -> USMSMeter:
        """Retrieve a specific USMSMeter object by its ID or meter number."""
        if isinstance(meter_no, int):
            meter_no = str(meter_no)

        for meter in self.meters:
            if meter_no in (meter.id, meter.no):
                return meter

        raise USMSMeterNumberError(meter_no)

    def get_latest_update(self) -> None:
        """Determine the most recent update timestamp among all meters."""
        latest_update = datetime.min.replace(tzinfo=BRUNEI_TZ)

        for meter in self.meters:
            last_update = meter.get_last_updated()
            latest_update = max(latest_update, last_update)

        return latest_update

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
        try:
            # Clone the cookies manually, but use a plain httpx client
            with httpx.Client(cookies=self.session.cookies) as temp_client:
                response = temp_client.get(f"{USMSClient.BASE_URL}/AccountInfo")
                is_expired = self.session.auth.is_expired(response)

                if is_expired:
                    logger.debug(f"[{self.username}] Account is NOT authenticated")
                else:
                    logger.debug(f"[{self.username}] Account is authenticated")

                return not is_expired
        except httpx.HTTPError as error:
            logger.warning(f"[{self.username}] Login check failed: {error}")
            return False
