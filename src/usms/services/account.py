"""Base USMS Account Service."""

from abc import ABC
from datetime import datetime
from typing import TYPE_CHECKING

from usms.config.constants import REFRESH_INTERVAL, UPDATE_INTERVAL
from usms.core.client import USMSClient
from usms.exceptions.errors import USMSMeterNumberError
from usms.models.account import USMSAccount as USMSAccountModel
from usms.storage.base_storage import BaseUSMSStorage
from usms.utils.decorators import requires_init
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.services.meter import BaseUSMSMeter
    from usms.storage.base_storage import BaseUSMSStorage


class BaseUSMSAccount(ABC, USMSAccountModel):
    """Base USMS Account Service to be inherited."""

    session: USMSClient

    last_refresh: datetime

    def __init__(
        self,
        session: USMSClient,
        storage_manager: "BaseUSMSStorage" = None,
    ) -> None:
        """Initialize reg_no variable and USMSAuth object."""
        self.session = session
        self.storage_manager = storage_manager

        self.reg_no = self.session.username

        self.last_refresh = datetime.now().astimezone()

        self._initialized = False

    @requires_init
    def get_meter(self, meter_no: str | int) -> "BaseUSMSMeter":
        """Return meter associated with the given meter number."""
        for meter in self.meters:
            if str(meter_no) in (str(meter.no), (meter.id)):
                return meter
        raise USMSMeterNumberError(meter_no)

    @requires_init
    def get_latest_update(self) -> datetime:
        """Return the latest time a meter was updated."""
        latest_update = datetime.fromtimestamp(0).astimezone()
        for meter in self.meters:
            latest_update = max(latest_update, meter.get_last_updated())
        return latest_update

    @requires_init
    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now().astimezone()
        latest_update = self.get_latest_update()

        # Interval between checking for new updates
        logger.debug(f"[{self.reg_no}] update_interval: {UPDATE_INTERVAL}")
        logger.debug(f"[{self.reg_no}] refresh_interval: {REFRESH_INTERVAL}")

        # Elapsed time since the meter was last updated by USMS
        time_since_last_update = now - latest_update
        logger.debug(f"[{self.reg_no}] last_update: {latest_update}")
        logger.debug(f"[{self.reg_no}] time_since_last_update: {time_since_last_update}")

        # Elapsed time since a refresh was last attempted
        time_since_last_refresh = now - self.last_refresh
        logger.debug(f"[{self.reg_no}] last_refresh: {self.last_refresh}")
        logger.debug(f"[{self.reg_no}] time_since_last_refresh: {time_since_last_refresh}")

        # If 60 minutes has passed since meter was last updated by USMS
        if time_since_last_update > UPDATE_INTERVAL:
            logger.debug(f"[{self.reg_no}] time_since_last_update > update_interval")
            # If 15 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > REFRESH_INTERVAL:
                logger.debug(f"[{self.reg_no}] time_since_last_refresh > refresh_interval")
                logger.debug(f"[{self.reg_no}] Account is due for an update")
                return True

            logger.debug(f"[{self.reg_no}] time_since_last_refresh < refresh_interval")
            logger.debug(f"[{self.reg_no}] Account is NOT due for an update")
            return False

        logger.debug(f"[{self.reg_no}] time_since_last_update < update_interval")
        logger.debug(f"[{self.reg_no}] Account is NOT due for an update")
        return False
