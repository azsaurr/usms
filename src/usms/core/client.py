"""
USMS Client Module.

This module defines httpx client class
customized especially to send requests
and receive responses with USMS pages.
"""

from abc import ABC, abstractmethod

import httpx
import lxml.html

from usms.core.auth import USMSAuth
from usms.utils.decorators import requires_init
from usms.utils.helpers import create_ssl_context
from usms.utils.logging_config import logger


class BaseUSMSClient(ABC):
    """Base HTTP client for interacting with USMS."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    _asp_state: dict

    def __init__(self, auth: USMSAuth) -> None:
        """Initialize auth for this client."""
        self.auth = auth
        self.ssl_context = None

        self._initialized = False

    def initialize(self) -> None:
        """Actual initialization logic of Client object."""
        if self.ssl_context is None:
            super().__init__(auth=self.auth)
        else:
            super().__init__(auth=self.auth, verify=self.ssl_context)

        self.base_url = self.BASE_URL
        self.http2 = True
        self.timeout = 30
        self.event_hooks["response"] = [self._update_asp_state]

        self._asp_state = {}

        self._initialized = True

    @requires_init
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

    @requires_init
    def _extract_asp_state(self, response_content: bytes) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        try:
            response_html = lxml.html.fromstring(response_content)

            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                if hidden_input.value:
                    self._asp_state[hidden_input.name] = hidden_input.value
        except Exception as error:  # noqa: BLE001
            logger.error(f"Failed to parse ASP.NET state: {error}")

    @requires_init
    @abstractmethod
    async def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""


class USMSClient(BaseUSMSClient, httpx.Client):
    """Sync HTTP client for interacting with USMS."""

    @classmethod
    def create(cls, auth: USMSAuth) -> "USMSClient":
        """Initialize and return instance of this class as an object."""
        self = cls(auth)
        self.initialize()
        return self

    @requires_init
    def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        super()._extract_asp_state(response.read())


class AsyncUSMSClient(BaseUSMSClient, httpx.AsyncClient):
    """Async HTTP client for interacting with USMS."""

    async def initialize(self) -> None:
        """Actual initialization logic of Client object."""
        self.ssl_context = await create_ssl_context()
        super().initialize()

    @classmethod
    async def create(cls, auth: USMSAuth) -> "AsyncUSMSClient":
        """Initialize and return instance of this class as an object."""
        self = cls(auth)
        await self.initialize()
        return self

    @requires_init
    async def post(self, url: str, data: dict | None = None) -> httpx.Response:
        """Send a POST request with ASP.NET hidden fields included."""
        return await super().post(url=url, data=data)

    @requires_init
    async def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        super()._extract_asp_state(await response.aread())
