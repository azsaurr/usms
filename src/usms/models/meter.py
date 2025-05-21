"""USMS Meter Module."""

import base64
from dataclasses import dataclass
from datetime import datetime

from usms.config.constants import BRUNEI_TZ


@dataclass
class USMSMeter:
    """Represents a USMS meter."""

    """USMS Meter class attributes."""
    address: str
    kampong: str
    mukim: str
    district: str
    postcode: str

    no: str
    id: str  # base64 encoded meter no

    type: str
    # customer_type: str  # currently not fetched  # noqa: ERA001

    remaining_unit: float
    remaining_credit: float

    last_update: datetime

    status: str

    def update_from_json(self, data: dict[str, str]) -> None:
        """Update base attributes from a json/dict data."""
        allowed = {"status", "address", "kampong", "mukim", "district", "postcode"}
        for key, value in data.items():
            if key in allowed:
                setattr(self, key, value)

        no = data.get("no", "")
        if no:
            self.no = no
            self.id = base64.b64encode(no.encode()).decode()

        remaining_unit = data.get("remaining_unit", "").split()
        if remaining_unit:
            self.remaining_unit = float(remaining_unit[0].replace(",", ""))
            self.unit = remaining_unit[-1]
            self.type = "Water" if remaining_unit[-1] == "m³" else "Electricity"

        remaining_credit = data.get("remaining_credit", "").split("$")[-1]
        if remaining_credit:
            self.remaining_credit = float(remaining_credit.replace(",", ""))

        last_update = data.get("last_update", "")
        if last_update:
            date = last_update.split()[0].split("/")
            time = last_update.split()[1].split(":")
            self.last_update = datetime(
                int(date[2]),
                int(date[1]),
                int(date[0]),
                hour=int(time[0]),
                minute=int(time[1]),
                second=int(time[2]),
                tzinfo=BRUNEI_TZ,
            )
        else:
            self.last_update = datetime.fromtimestamp(0).astimezone()

    @property
    def is_active(self) -> bool:
        """Return True if the meter status is active."""
        return self.status == "ACTIVE"
