"""
USMS Client Module.

This module defines custom client class
customized especially to send requests
and receive responses with USMS pages.
"""

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from usms.core.auth import USMSClientAuthMixin
from usms.core.state_manager import USMSClientASPStateMixin

if TYPE_CHECKING:
    from usms.core.protocols import HTTPXClientProtocol, HTTPXResponseProtocol


class USMSClient(USMSClientASPStateMixin, USMSClientAuthMixin):
    """USMS Client for interacting with USMS."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    def __init__(
        self,
        username: str,
        password: str,
        client: "HTTPXClientProtocol",
    ) -> None:
        """Initialize USMS Client."""
        # Initialize mixin classes
        USMSClientAuthMixin.__init__(self, username=username, password=password)
        USMSClientASPStateMixin.__init__(self)

        client.follow_redirects = True
        self.async_mode = inspect.iscoroutinefunction(client.get)

        self.client = client

    def get(self, url: str, **kwargs: Any) -> Callable:
        """Return a sync/async GET request method."""
        if self.async_mode:
            return self._request_async("get", url, **kwargs)  # has to be awaited
        return self._request_sync("get", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Callable:
        """Return a sync/async POST request method, with ASP.net state injection."""
        kwargs["data"] = self._inject_asp_state(kwargs.get("data", {}))

        if self.async_mode:
            return self._request_async("post", url, **kwargs)  # has to be awaited
        return self._request_sync("post", url, **kwargs)

    def _request_sync(self, http_method: str, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send sync HTTP request, with URL building, auto-reauth and ASP.net state extraction."""
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        request_method = getattr(self.client, http_method.lower())

        for _ in range(3):
            response = request_method(url, **kwargs)
            if self.is_expired(response):
                self.authenticate()
            else:
                break

        response_content = response.read()
        self._extract_asp_state(response_content)

        return response

    async def _request_async(
        self, http_method: str, url: str, **kwargs: Any
    ) -> "HTTPXResponseProtocol":
        """Send async HTTP request, with URL building, auto-reauth and ASP.net state extraction."""
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        request_method = getattr(self.client, http_method.lower())

        for _ in range(3):
            response = await request_method(url, **kwargs)
            if await self.is_expired(response):
                await self.authenticate()
            else:
                break

        response_content = await response.aread()
        self._extract_asp_state(response_content)

        return response

    @property
    def username(self) -> str:
        """Account username."""
        return self._username
