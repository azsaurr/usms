"""Base Storage Manager for USMS."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
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

    def insert_or_replace_many(
        self,
        records: Iterable[tuple[str, int, float, int]],
    ) -> None:
        """
        Insert or replace many consumption records at once.

        Backfilling a meter's history writes thousands of rows, and doing that one
        record at a time is quadratic for file-backed storage. Backends should
        override this with a single bulk write; the default keeps any third-party
        storage working by falling back to repeated single inserts.
        """
        for meter_no, timestamp, consumption, last_checked in records:
            self.insert_or_replace(meter_no, timestamp, consumption, last_checked)

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
