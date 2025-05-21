"""USMS Account Module."""

from dataclasses import dataclass

from usms.models.meter import USMSMeter


@dataclass
class USMSAccount:
    """Represents a USMS account."""

    """USMS Account class attributes."""
    reg_no: str
    name: str
    # contact_no: str  # currently not fetched  # noqa: ERA001
    # email: str  # currently not fetched  # noqa: ERA001
    meters: list[USMSMeter]

    def update_from_json(self, data: dict[str, str]) -> None:
        """Update base attributes from a json/dict data."""
        allowed = {"name"}
        for key, value in data.items():
            if key in allowed:
                setattr(self, key, value)

        if hasattr(self, "meters"):
            for meter in self.meters:
                for meter_data in data.get("meters", []):
                    if meter.no == meter_data["no"]:
                        meter.update_from_json(meter_data)
                        continue
