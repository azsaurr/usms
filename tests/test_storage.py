"""Test the storage backends."""

import pathlib

import pytest

from usms.storage.base_storage import BaseUSMSStorage
from usms.storage.csv_storage import CSVUSMSStorage
from usms.storage.sqlite_storage import SQLiteUSMSStorage

METER = "55014488"
OTHER_METER = "2402007817"


@pytest.fixture(params=["csv", "sqlite"])
def storage(request, tmp_path: pathlib.Path) -> BaseUSMSStorage:
    """Return each storage backend in turn, so both honour the same contract."""
    if request.param == "csv":
        return CSVUSMSStorage(tmp_path / "usms.csv")
    return SQLiteUSMSStorage(tmp_path / "usms.db")


def _records(count: int, *, meter: str = METER, offset: float = 0.0) -> list[tuple]:
    """Return `count` consecutive hourly records."""
    return [(meter, 1700000000 + hour * 3600, hour + offset, 1700000000) for hour in range(count)]


def test_bulk_insert_round_trip(storage) -> None:
    """Test that bulk-inserted records come back intact."""
    storage.insert_or_replace_many(_records(50))

    stored = storage.get_all_consumptions(METER)

    assert len(stored) == 50
    assert {timestamp for timestamp, _, _ in stored} == {record[1] for record in _records(50)}


def test_bulk_insert_replaces_rather_than_duplicates(storage) -> None:
    """Test that re-inserting the same timestamps updates in place."""
    storage.insert_or_replace_many(_records(10))
    storage.insert_or_replace_many(_records(10, offset=100.0))

    stored = storage.get_all_consumptions(METER)

    assert len(stored) == 10
    assert all(consumption >= 100.0 for _, consumption, _ in stored)


def test_bulk_insert_mixes_new_and_existing(storage) -> None:
    """Test that a batch containing both updates and new rows lands correctly."""
    storage.insert_or_replace_many(_records(5))
    storage.insert_or_replace_many(_records(8, offset=50.0))

    stored = {timestamp: value for timestamp, value, _ in storage.get_all_consumptions(METER)}

    assert len(stored) == 8
    assert stored[1700000000] == pytest.approx(50.0)
    assert stored[1700000000 + 7 * 3600] == pytest.approx(57.0)


def test_bulk_insert_is_scoped_per_meter(storage) -> None:
    """Test that one meter's records never leak into another's."""
    storage.insert_or_replace_many(_records(4))
    storage.insert_or_replace_many(_records(6, meter=OTHER_METER))

    assert len(storage.get_all_consumptions(METER)) == 4
    assert len(storage.get_all_consumptions(OTHER_METER)) == 6


def test_bulk_insert_of_nothing_is_harmless(storage) -> None:
    """Test that an empty batch leaves existing records untouched."""
    storage.insert_or_replace_many(_records(3))
    storage.insert_or_replace_many([])

    assert len(storage.get_all_consumptions(METER)) == 3


def test_bulk_insert_accepts_a_generator(storage) -> None:
    """Test that a generator is accepted, since the caller streams records in."""
    storage.insert_or_replace_many(record for record in _records(5))

    assert len(storage.get_all_consumptions(METER)) == 5


def test_single_and_bulk_insert_agree(storage) -> None:
    """Test that the bulk path produces the same result as repeated single inserts."""
    for record in _records(6):
        storage.insert_or_replace(*record)
    one_at_a_time = sorted(storage.get_all_consumptions(METER))

    storage.insert_or_replace_many(_records(6))

    assert sorted(storage.get_all_consumptions(METER)) == one_at_a_time
