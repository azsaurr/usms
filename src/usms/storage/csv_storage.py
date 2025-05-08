"""CSV Wrapper."""

import csv
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile


class CSVStorage:
    """CSV Wrapper for Consumption Data."""

    def __init__(self, file_path: Path) -> None:
        """Initialize the CSV wrapper."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            self.file_path.write_text("meter_no,timestamp,consumption,last_checked\n")

    def insert_or_replace(
        self,
        meter_no: str,
        timestamp: int,
        consumption: float,
        last_checked: int,
    ) -> None:
        """Efficiently insert or replace a consumption record."""
        updated = False

        with NamedTemporaryFile(
            "w", delete=False, newline="", dir=self.file_path.parent
        ) as temp_file:
            with self.file_path.open("r", newline="") as infile, temp_file:
                reader = csv.reader(infile)
                writer = csv.writer(temp_file)

                # Write header
                header = next(reader, None)
                if header:
                    writer.writerow(header)

                # Write rows with replacement
                for row in reader:
                    if row[0] == meter_no and int(row[1]) == timestamp:
                        writer.writerow([meter_no, timestamp, consumption, last_checked])
                        updated = True
                    else:
                        writer.writerow(row)

                # Append new row if it wasn't updated
                if not updated:
                    writer.writerow([meter_no, timestamp, consumption, last_checked])

            # Replace original file with updated temp file
            shutil.move(temp_file.name, self.file_path)

    def get_consumption(
        self,
        meter_no: str,
        timestamp: int,
    ) -> tuple[str, float, str] | None:
        """Retrieve a specific consumption record."""
        with self.file_path.open("r") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if row[0] == meter_no and int(row[1]) == timestamp:
                    return int(row[1]), float(row[2]), int(row[3])
        return None

    def get_all_consumptions(
        self,
        meter_no: str,
    ) -> list[tuple[str, float, str]]:
        """Retrieve all consumption records for a specific meter_no."""
        with self.file_path.open("r") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            return [
                (
                    int(row[1]),
                    float(row[2]),
                    int(row[3]),
                )
                for row in reader
                if row[0] == meter_no
            ]
