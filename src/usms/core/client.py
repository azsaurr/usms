"""
USMS Client Module.

This module defines httpx client class
customized especially to send requests
and receive responses with USMS pages.
"""

from abc import ABC, abstractmethod
from typing import Any

from usms.core.protocols import HTTPClient
from usms.core.state_manager import USMSASPStateMixin


class BaseUSMSClient(ABC, USMSASPStateMixin):
    """Base USMS Client for shared sync and async logics."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    def __init__(self, client: HTTPClient) -> None:
        """Initialize auth for this client."""
        super().__init__()  # Initialize ASPStateMixin
        self.client = client

    @abstractmethod
    def get(self, url: str, data: dict | None = None) -> Any:
        """Abstract GET method for derived clients."""

    @abstractmethod
    def post(self, url: str, data: dict | None = None) -> Any:
        """Abstract POST method for derived clients."""

    def get_username(self) -> str | None:
        """Return the username from the client's auth."""
        if self.client.auth is not None:
            return getattr(self.client.auth, "_username", None)
        return None

    def _build_url(self, url: str) -> str:
        """Ensure the URL is fully qualified."""
        return url if url.startswith("http") else f"{self.BASE_URL}{url}"


class USMSClient(BaseUSMSClient):
    """Sync HTTP client for interacting with USMS."""

    def get(self, url: str, **kwargs: Any) -> Any:
        """Send a synchronous GET request with ASP.NET state extraction."""
        response = self.client.get(self._build_url(url), **kwargs)
        response.raise_for_status()

        self._extract_asp_state(self._get_response_content(response))
        return response

    def post(self, url: str, data: dict | None = None, **kwargs: Any) -> Any:
        """Send a synchronous POST request with ASP.NET state."""
        data = self._inject_asp_state(data)
        response = self.client.post(self._build_url(url), data=data, **kwargs)
        response.raise_for_status()

        self._extract_asp_state(self._get_response_content(response))
        return response

    def _get_response_content(self, response: Any) -> bytes:
        """Safely extract response content, compatible with various client types."""
        # httpx sync
        if hasattr(response, "content"):
            return response.content

        # requests
        if hasattr(response, "text"):
            return response.text.encode("utf-8")

        # http.client
        if hasattr(response, "read") and callable(response.read):
            return response.read()

        # urllib3
        if hasattr(response, "data"):
            return response.data

        msg = "Unable to extract response content. Unsupported client type."
        raise ValueError(msg)


class AsyncUSMSClient(BaseUSMSClient):
    """Async HTTP client for interacting with USMS."""

    async def get(self, url: str, **kwargs: Any) -> Any:
        """Send an asynchronous GET request with ASP.NET state extraction."""
        response = await self.client.get(self._build_url(url), **kwargs)
        response.raise_for_status()

        self._extract_asp_state(await self._get_response_content(response))
        return response

    async def post(self, url: str, data: dict | None = None, **kwargs: Any) -> Any:
        """Send an asynchronous POST request with ASP.NET state."""
        data = self._inject_asp_state(data)
        response = await self.client.post(self._build_url(url), data=data, **kwargs)
        response.raise_for_status()

        self._extract_asp_state(await self._get_response_content(response))
        return response

    async def _get_response_content(self, response: Any) -> bytes:
        """Safely extract response content, compatible with various client types."""
        # httpx async
        if hasattr(response, "aread"):
            return await response.aread()

        # aiohttp
        if hasattr(response, "read"):
            return await response.read()
        if hasattr(response, "text") and callable(response.text):
            return (await response.text()).encode("utf-8")

        msg = "Unable to extract response content. Unsupported client type."
        raise ValueError(msg)
