"""SQLite Database Wrapper."""

import sqlite3
from pathlib import Path

from usms.storage.base_storage import BaseUSMSStorage


class SQLiteUSMSStorage(BaseUSMSStorage):
    """SQLite Database Wrapper for Consumption Data."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS consumption (
        meter_no TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        consumption REAL NOT NULL,
        last_checked INTEGER NOT NULL,
        PRIMARY KEY (meter_no, timestamp)
    );
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the database connection."""
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self._create_schema()

    def _create_schema(self):
        """Create the database schema."""
        with self.conn:
            self.conn.executescript(self.SCHEMA)

    def insert_or_replace(
        self,
        meter_no: str,
        timestamp: int,
        consumption: float,
        last_checked: int,
    ) -> None:
        """Insert or replace a consumption record."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO consumption (
                    meter_no, timestamp, consumption, last_checked
                ) VALUES (?, ?, ?, ?)
                """,
                (meter_no, timestamp, consumption, last_checked),
            )

    def get_consumption(
        self,
        meter_no: str,
        timestamp: str,
    ) -> tuple[float, str] | None:
        """Retrieve a specific consumption record."""
        with self.conn:
            row = self.conn.execute(
                """
                SELECT consumption, last_checked FROM consumption
                WHERE meter_no = ? AND timestamp = ?
                """,
                (meter_no, timestamp),
            ).fetchone()
        return row

    def get_all_consumptions(
        self,
        meter_no: str,
    ) -> list[tuple[str, float, str]]:
        """Retrieve all consumption records for a specific meter_no."""
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT timestamp, consumption, last_checked
                FROM consumption
                WHERE meter_no = ?
                ORDER BY timestamp ASC
                """,
                (meter_no,),
            ).fetchall()
        return rows

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()
