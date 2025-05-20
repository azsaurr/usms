"""Base USMS Account Service."""

from abc import ABC
from datetime import datetime

from usms.config.constants import REFRESH_INTERVAL, UPDATE_INTERVAL
from usms.core.client import USMSClient
from usms.exceptions.errors import USMSMeterNumberError
from usms.models.account import USMSAccount as USMSAccountModel
from usms.services.meter import BaseUSMSMeter
from usms.storage.base_storage import BaseUSMSStorage
from usms.utils.decorators import requires_init
from usms.utils.logging_config import logger


class BaseUSMSAccount(ABC, USMSAccountModel):
    """Base USMS Account Service to be inherited."""

    session: USMSClient

    last_refresh: datetime

    def __init__(
        self,
        session: USMSClient,
        storage_manager: BaseUSMSStorage | None = None,
    ) -> None:
        """Initialize username variable and USMSAuth object."""
        self.session = session
        self.storage_manager = storage_manager

        self.username = self.session.username

        self.last_refresh = datetime.now().astimezone()

        self._initialized = False

    def from_json(self, data: dict) -> None:
        """Initialize base attributes from a json/dict data."""
        self.name = data.get("name", "")

        if hasattr(self, "meters"):
            for meter in self.get_meters():
                for meter_data in data.get("meters", []):
                    if meter.no == meter_data["no"]:
                        meter.from_json(meter_data)
                        continue

    @requires_init
    def get_meters(self) -> list[BaseUSMSMeter]:
        """Return list of all meters associated with this account."""
        return self.meters

    @requires_init
    def get_meter(self, meter_no: str | int) -> BaseUSMSMeter:
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
