"""
Test how an account decides it has new data, and checks its session.

Both changed in October 2026, when USMS began reporting an electricity meter's
"Last Updated" as a bare date: comparing that date alone found new data once a day,
and the fallback session check it then hit had been broken all along.
"""

import asyncio

from usms.models.meter import USMSMeter
from usms.services.async_.account import AsyncUSMSAccount
from usms.services.sync.account import USMSAccount

CARD = {
    "no": "12345678",
    "remaining_unit": "1,971.317 kWh",
    "remaining_credit": "$174.10",
    "last_update": "13/10/2026",
}


def _account(cls: type = USMSAccount):
    """Return an initialised account holding one meter built from CARD."""
    meter = USMSMeter.__new__(USMSMeter)
    meter.update_from_json(CARD)
    account = cls.__new__(cls)
    account.meters = [meter]
    account._initialized = True  # noqa: SLF001
    account.reg_no = "00000001"
    return account


def _fresh(**changes: str) -> dict:
    return {"meters": [{**CARD, **changes}]}


def test_same_card_is_not_new() -> None:
    """Test that an unchanged card is not reported as new data."""
    assert not _account().has_new_data(_fresh())


def test_credit_moving_within_the_same_date_is_new() -> None:
    """Test that new hourly figures count even though the date has not moved."""
    account = _account()

    assert account.has_new_data(_fresh(remaining_credit="$173.25"))
    assert account.has_new_data(_fresh(remaining_unit="1,960.747 kWh"))


def test_a_later_last_update_is_new() -> None:
    """Test that the date advancing is still new data on its own."""
    assert _account().has_new_data(_fresh(last_update="14/10/2026"))


def test_an_unknown_meter_is_new() -> None:
    """Test that a meter the account does not hold yet counts as new data."""
    assert _account().has_new_data(_fresh(no="87654321"))


def test_has_new_data_leaves_the_meter_untouched() -> None:
    """Test that checking parses a copy, so the held meter keeps its values."""
    account = _account()

    account.has_new_data(_fresh(remaining_credit="$1.00"))

    assert account.meters[0].remaining_credit == 174.10


class _Response:
    status_code = 200

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode()

    async def aread(self) -> bytes:
        return self._text.encode()


class _SyncSession:
    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, url: str, **kwargs: object) -> _Response:
        return _Response(self.text)

    def is_expired(self, response: _Response) -> bool:
        return "Session Has Expired" in response.read().decode()


class _AsyncSession(_SyncSession):
    async def get(self, url: str, **kwargs: object) -> _Response:
        return _Response(self.text)

    async def is_expired(self, response: _Response) -> bool:
        return "Session Has Expired" in (await response.aread()).decode()


def test_sync_is_authenticated_asks_the_session() -> None:
    """Test the sync check, which used to raise AttributeError on `self.auth`."""
    account = _account()
    account.session = _SyncSession("<html>AccountInfo</html>")
    assert account.is_authenticated()

    account.session = _SyncSession("Your Session Has Expired, Please Login Again.")
    assert not account.is_authenticated()


def test_async_is_authenticated_awaits_the_session() -> None:
    """Test the async check, whose session's is_expired is a coroutine."""
    account = _account(AsyncUSMSAccount)
    account.session = _AsyncSession("<html>AccountInfo</html>")
    assert asyncio.run(account.is_authenticated())

    account.session = _AsyncSession("Your Session Has Expired, Please Login Again.")
    assert not asyncio.run(account.is_authenticated())
