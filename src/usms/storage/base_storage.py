"""Base Storage Manager for USMS."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseUSMSStorage(ABC):
    """Base USMS Client for shared sync and async logics."""

    @abstractmethod
    def __init__(self, file_path: Path) -> None:
        """Initialize the storage manager."""

    @abstractmethod
    def insert_or_replace(
        self,
        meter_no: str,
        timestamp: int,
        consumption: float,
        last_checked: int,
    ) -> None:
        """Insert or replace a consumption record."""

    @abstractmethod
    def get_consumption(
        self,
        meter_no: str,
        timestamp: str,
    ) -> tuple[float, str] | None:
        """Retrieve a specific consumption record."""

    @abstractmethod
    def get_all_consumptions(
        self,
        meter_no: str,
    ) -> list[tuple[str, float, str]]:
        """Retrieve all consumption records for a specific meter_no."""
