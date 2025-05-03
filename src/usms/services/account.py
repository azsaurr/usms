"""Base USMS Account Service."""

from abc import ABC
from datetime import datetime

import httpx
import lxml.html

from usms.config.constants import REFRESH_INTERVAL, UPDATE_INTERVAL
from usms.core.auth import USMSAuth
from usms.exceptions.errors import USMSMeterNumberError
from usms.models.account import USMSAccount as USMSAccountModel
from usms.services.async_.meter import AsyncUSMSMeter
from usms.services.meter import BaseUSMSMeter
from usms.services.sync.meter import USMSMeter
from usms.utils.decorators import requires_init
from usms.utils.logging_config import logger


class BaseUSMSAccount(ABC, USMSAccountModel):
    """Base USMS Account Service to be inherited."""

    username: str
    auth: USMSAuth

    last_refresh: datetime

    def __init__(self, username: str, password: str) -> None:
        """Initialize username variable and USMSAuth object."""
        self.username = username
        self.auth = USMSAuth(username, password)

        self.last_refresh = datetime.now().astimezone()

        self._initialized = False

    @staticmethod
    def parse_more_info(response: httpx.Response | bytes) -> dict:
        """Parse data from account info page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        reg_no = response_html.find(""".//span[@id="ASPxFormLayout1_lblIDNumber"]""").text_content()
        name = response_html.find(""".//span[@id="ASPxFormLayout1_lblName"]""").text_content()
        contact_no = response_html.find(
            """.//span[@id="ASPxFormLayout1_lblContactNo"]"""
        ).text_content()
        email = response_html.find(""".//span[@id="ASPxFormLayout1_lblEmail"]""").text_content()

        return {
            "reg_no": reg_no,
            "name": name,
            "contact_no": contact_no,
            "email": email,
        }

    @staticmethod
    def parse_info(response: httpx.Response | bytes) -> dict:
        """Parse data from account home page and return as json."""
        if isinstance(response, httpx.Response):
            response_html = lxml.html.fromstring(response.content)
        elif isinstance(response, bytes):
            response_html = lxml.html.fromstring(response)
        else:
            response_html = response

        name = (
            response_html.find(""".//td[@id="ASPxCardView1_DXCardLayout0_4"]""")
            .findall(".//td")[1]
            .text_content()
        )

        meters = []
        for meter_card in response_html.findall(""".//td[@class="dxcvCard"]"""):
            meter_data = BaseUSMSMeter.parse_info(meter_card)
            meters.append(meter_data)

        return {
            "name": name,
            "meters": meters,
        }

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        for key, value in data.items():
            if key == "meters":
                continue
            setattr(self, key, value)

        if hasattr(self, "meters"):
            for meter in self.get_meters():
                for meter_data in data.get("meters", []):
                    if meter.no == meter_data["no"]:
                        meter.from_json(meter_data)
                        continue

    @requires_init
    def get_meters(self) -> list[USMSMeter | AsyncUSMSMeter]:
        """Return list of all meters associated with this account."""
        return self.meters

    @requires_init
    def get_meter(self, meter_no: str | int) -> USMSMeter | AsyncUSMSMeter:
        """Return meter associated with the given meter number."""
        for meter in self.get_meters():
            if str(meter_no) in (str(meter.no), (meter.id)):
                return meter
        raise USMSMeterNumberError(meter_no)

    @requires_init
    def get_latest_update(self) -> datetime:
        """Return the latest time a meter was updated."""
        latest_update = datetime.fromtimestamp(0).astimezone()
        for meter in self.get_meters():
            latest_update = max(latest_update, meter.get_last_updated())
        return latest_update

    @requires_init
    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now().astimezone()
        latest_update = self.get_latest_update()

        # Interval between checking for new updates
        logger.debug(f"[{self.username}] update_interval: {UPDATE_INTERVAL}")
        logger.debug(f"[{self.username}] refresh_interval: {REFRESH_INTERVAL}")

        # Elapsed time since the meter was last updated by USMS
        time_since_last_update = now - latest_update
        logger.debug(f"[{self.username}] last_update: {latest_update}")
        logger.debug(f"[{self.username}] time_since_last_update: {time_since_last_update}")

        # Elapsed time since a refresh was last attempted
        time_since_last_refresh = now - self.last_refresh
        logger.debug(f"[{self.username}] last_refresh: {self.last_refresh}")
        logger.debug(f"[{self.username}] time_since_last_refresh: {time_since_last_refresh}")

        # If 60 minutes has passed since meter was last updated by USMS
        if time_since_last_update > UPDATE_INTERVAL:
            logger.debug(f"[{self.username}] time_since_last_update > update_interval")
            # If 15 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > REFRESH_INTERVAL:
                logger.debug(f"[{self.username}] time_since_last_refresh > refresh_interval")
                logger.debug(f"[{self.username}] Account is due for an update")
                return True

            logger.debug(f"[{self.username}] time_since_last_refresh < refresh_interval")
            logger.debug(f"[{self.username}] Account is NOT due for an update")
            return False

        logger.debug(f"[{self.username}] time_since_last_update < update_interval")
        logger.debug(f"[{self.username}] Account is NOT due for an update")
        return False
