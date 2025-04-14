"""
USMS Account Module.

This module defines the USMSAccount class,
which represents a user account in the USMS system.
It provides methods to retrieve account details,
manage associated meters and handle user sessions.
"""

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
