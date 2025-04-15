"""USMS Meter Module."""

from dataclasses import dataclass
from datetime import datetime


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
    customer_type: str

    remaining_unit: float
    remaining_credit: float

    last_update: datetime | None

    status: str
