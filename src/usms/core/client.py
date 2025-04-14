"""
USMS Client Module.

This module defines httpx client class
customized especially to send requests
and receive responses with USMS pages.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union

import httpx
import lxml.html

from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.core.auth import USMSAuth


class BaseUSMSClient(ABC):
    """Base HTTP client for interacting with USMS."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    _asp_state: dict

    @classmethod
    @abstractmethod
    def create(
        cls,
        auth: "USMSAuth",
    ) -> Union["USMSClient", "AsyncUSMSClient"]:
        """Construct the client without blocking in async context."""

    def __actual_init__(
        self,
        auth: "USMSAuth",
    ) -> Union["USMSClient", "AsyncUSMSClient"]:
        """Initialize logic."""
        super().__init__(auth=auth)
        self.base_url = self.BASE_URL
        self.http2 = True
        self.timeout = 30
        self.event_hooks["response"] = [self._update_asp_state]

        self._asp_state = {}
        return self

    def post(self, url: str, data: dict | None = None) -> httpx.Response:
        """Send a POST request with ASP.NET hidden fields included."""
        if data is None:
            data = {}

        # Merge stored ASP state with request data
        if self._asp_state and data:
            for asp_key, asp_value in self._asp_state.items():
                if not data.get(asp_key):
                    data[asp_key] = asp_value

        return super().post(url=url, data=data)

    def _extract_asp_state(self, response_content: bytes) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        try:
            response_html = lxml.html.fromstring(response_content)

            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                if hidden_input.value:
                    self._asp_state[hidden_input.name] = hidden_input.value
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse ASP.NET state: {e}")

    @abstractmethod
    async def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""


class USMSClient(BaseUSMSClient, httpx.Client):
    """Sync HTTP client for interacting with USMS."""

    def __init__(self, *args, **kwargs):
        """Prevent direct init; use `create()` instead."""
        msg = "Use `USMSClient.create(auth)` to initialize this client."
        raise RuntimeError(msg)

    @classmethod
    def create(cls, auth: "USMSAuth") -> "USMSClient":
        """Construct the client without blocking in async context."""
        return super().__new__(cls).__actual_init__(auth)

    def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        super()._extract_asp_state(response.read())


class AsyncUSMSClient(BaseUSMSClient, httpx.AsyncClient):
    """Async HTTP client for interacting with USMS."""

    def __init__(self, *args, **kwargs):
        """Prevent direct init; use `create()` instead."""
        msg = "Use `AsyncUSMSClient.create(auth)` to initialize this client."
        raise RuntimeError(msg)

    @classmethod
    async def create(cls, auth: "USMSAuth") -> "AsyncUSMSClient":
        """Construct the client without blocking in async context."""
        return super().__new__(cls).__actual_init__(auth)

    async def post(self, url: str, data: dict | None = None) -> httpx.Response:
        """Send a POST request with ASP.NET hidden fields included."""
        return await super().post(url=url, data=data)

    async def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        super()._extract_asp_state(await response.aread())
