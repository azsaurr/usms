"""USMS Account Module."""

from dataclasses import dataclass

from usms.models.meter import USMSMeter


@dataclass
class USMSAccount:
    """Represents a USMS account."""

    """USMS Account class attributes."""
    reg_no: str
    name: str
    contact_no: str
    email: str
    meters: list[USMSMeter]
