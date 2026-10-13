"""Base USMS Account Service."""

import copy
from abc import ABC
from datetime import datetime
from typing import TYPE_CHECKING

from usms.config.constants import BRUNEI_TZ, REFRESH_INTERVAL, UPDATE_INTERVAL
from usms.core.client import BaseUSMSClient
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

    session: BaseUSMSClient

    last_refresh: datetime

    def __init__(
        self,
        session: BaseUSMSClient,
        storage_manager: "BaseUSMSStorage | None" = None,
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
    def has_new_data(self, fresh_info: dict) -> bool:
        """
        Return True if freshly fetched account info holds anything the meters lack.

        `last_update` alone stopped being enough in October 2026, when USMS began
        reporting it as a bare date for electricity meters as well: it now advances
        once a day, while the credit and units still change every hour. A meter is
        therefore also new when either of those moved. The fresh values are parsed
        by the meter's own `update_from_json`, on a copy, so nothing changes yet.
        """
        current = {meter.no: meter for meter in self.meters}
        for meter_data in fresh_info.get("meters", []):
            meter = current.get(meter_data.get("no"))
            if meter is None:
                return True

            fresh = copy.copy(meter)
            fresh.update_from_json(meter_data)
            if fresh.last_update > meter.last_update or (
                fresh.remaining_unit,
                fresh.remaining_credit,
            ) != (meter.remaining_unit, meter.remaining_credit):
                return True

        return False

    def get_latest_update(self) -> datetime:
        """Return the latest time a meter was updated."""
        latest_update = datetime.fromtimestamp(0, tz=BRUNEI_TZ)
        for meter in self.meters:
            latest_update = max(latest_update, meter.last_update)
        return latest_update

    @requires_init
    def is_update_due(self) -> bool:
        """Check if an update is due (based on last update timestamp)."""
        now = datetime.now().astimezone()
        latest_update = self.get_latest_update()

        # Interval between checking for new updates
        logger.debug("[%s] update_interval: %s", self.reg_no, UPDATE_INTERVAL)
        logger.debug("[%s] refresh_interval: %s", self.reg_no, REFRESH_INTERVAL)

        # Elapsed time since the meter was last updated by USMS
        time_since_last_update = now - latest_update
        logger.debug("[%s] last_update: %s", self.reg_no, latest_update)
        logger.debug("[%s] time_since_last_update: %s", self.reg_no, time_since_last_update)

        # Elapsed time since a refresh was last attempted
        time_since_last_refresh = now - self.last_refresh
        logger.debug("[%s] last_refresh: %s", self.reg_no, self.last_refresh)
        logger.debug("[%s] time_since_last_refresh: %s", self.reg_no, time_since_last_refresh)

        # If 60 minutes has passed since meter was last updated by USMS
        if time_since_last_update > UPDATE_INTERVAL:
            logger.debug("[%s] time_since_last_update > update_interval", self.reg_no)
            # If 15 minutes has passed since a refresh was last attempted
            if time_since_last_refresh > REFRESH_INTERVAL:
                logger.debug("[%s] time_since_last_refresh > refresh_interval", self.reg_no)
                logger.debug("[%s] Account is due for an update", self.reg_no)
                return True

            logger.debug("[%s] time_since_last_refresh < refresh_interval", self.reg_no)
            logger.debug("[%s] Account is NOT due for an update", self.reg_no)
            return False

        logger.debug("[%s] time_since_last_update < update_interval", self.reg_no)
        logger.debug("[%s] Account is NOT due for an update", self.reg_no)
        return False
