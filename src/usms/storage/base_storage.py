"""Base Storage Manager for USMS."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType
from typing import Self


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
        timestamp: int,
    ) -> tuple[int, float, int] | None:
        """Retrieve a specific consumption record."""

    @abstractmethod
    def get_all_consumptions(
        self,
        meter_no: str,
    ) -> list[tuple[int, float, int]]:
        """Retrieve all consumption records for a specific meter_no."""

    def close(self) -> None:  # noqa: B027
        """
        Release any resources the backend holds.

        Deliberately concrete rather than abstract: third-party backends that
        predate this method, and those that hold nothing open, stay valid
        without having to implement it.

        Backends that keep a handle open for their lifetime - SQLite keeps a
        connection - must override this; leaving one to be reclaimed by the
        garbage collector raises `ResourceWarning: unclosed database`.
        """

    def __enter__(self) -> Self:
        """Enter a context manager that closes the storage on exit."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the storage when leaving the context."""
        self.close()
