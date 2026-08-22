"""
USMS Client Module.

This module defines custom client class
customized especially to send requests
and receive responses with USMS pages.
"""

import asyncio
import inspect
import time
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from usms.core.auth import USMSClientAuthMixin
from usms.core.state_manager import USMSClientASPStateMixin
from usms.exceptions.errors import USMSLoginError, USMSPageResponseError
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.core.protocols import HTTPXClientProtocol, HTTPXResponseProtocol

# How many times a request is retried behind a re-authentication before giving up.
MAX_AUTH_ATTEMPTS = 3

# Status codes at or above this are treated as a failed request.
HTTP_ERROR_STATUS = 400

# Multiplied by the attempt number, so retries space out instead of hammering USMS.
REAUTH_BACKOFF = timedelta(seconds=1)

EXPIRED_SESSION_MESSAGE = (
    f"Session still expired after {MAX_AUTH_ATTEMPTS} re-authentication attempts. "
    "USMS allows only one active session per account, so another client may be "
    "logging in and invalidating this session."
)


class USMSClient(USMSClientASPStateMixin, USMSClientAuthMixin):
    """USMS Client for interacting with USMS."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    def __init__(
        self,
        username: str,
        password: str,
        client: "HTTPXClientProtocol",
        *,
        owns_client: bool = False,
    ) -> None:
        """
        Initialize USMS Client.

        `owns_client` records whether this client was created for us and may
        therefore be closed on our behalf. It stays False for a caller-supplied
        client - Home Assistant, for one, hands over a shared client that would
        break the rest of the application if we closed it.
        """
        # Initialize mixin classes
        USMSClientAuthMixin.__init__(self, username=username, password=password)
        USMSClientASPStateMixin.__init__(self)

        client.follow_redirects = True
        self.async_mode = inspect.iscoroutinefunction(client.get)

        self.client = client
        self._owns_client = owns_client

        # Serialises re-authentication so concurrent callers cannot invalidate each
        # other's session. Safe to build without a running loop since Python 3.10.
        self._reauth_lock = asyncio.Lock()

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

        for attempt in range(MAX_AUTH_ATTEMPTS):
            response = request_method(url, **kwargs)
            if not self.is_expired(response):
                break

            # USMS permits a single session per account, so re-authenticating races
            # with any other caller doing the same; back off before trying again.
            if attempt:
                time.sleep(REAUTH_BACKOFF.total_seconds() * attempt)
            self.authenticate()
        else:
            # Returning here would hand the caller a login page dressed up as data.
            raise USMSLoginError(EXPIRED_SESSION_MESSAGE)

        self._raise_for_status(response, url)

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

        for attempt in range(MAX_AUTH_ATTEMPTS):
            response = await request_method(url, **kwargs)
            if not await self.is_expired(response):
                break

            # USMS permits a single session per account, so concurrent callers must not
            # re-authenticate at the same time or each login invalidates the last.
            async with self._reauth_lock:
                if attempt:
                    await asyncio.sleep(REAUTH_BACKOFF.total_seconds() * attempt)
                await self.authenticate()
        else:
            # Returning here would hand the caller a login page dressed up as data.
            raise USMSLoginError(EXPIRED_SESSION_MESSAGE)

        self._raise_for_status(response, url)

        response_content = await response.aread()
        self._extract_asp_state(response_content)

        return response

    @staticmethod
    def _raise_for_status(response: "HTTPXResponseProtocol", url: str) -> None:
        """
        Raise if USMS answered with an HTTP error.

        Without this an outage is indistinguishable from an empty report: the error
        page parses to no rows, and the caller is told there is simply no consumption
        data for that date rather than that the request failed.
        """
        if response.status_code >= HTTP_ERROR_STATUS:
            logger.error("Request to %s failed with HTTP %s", url, response.status_code)
            raise USMSPageResponseError(url)

    def close(self) -> None:
        """Close the underlying client, if this instance created it."""
        if self._owns_client:
            self.client.close()

    async def aclose(self) -> None:
        """Close the underlying async client, if this instance created it."""
        if self._owns_client:
            await self.client.aclose()

    @property
    def username(self) -> str:
        """Account username."""
        return self._username
