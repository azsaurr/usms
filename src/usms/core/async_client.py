"""
USMS Client Module.

This module defines httpx client class
customized especially to send requests
and receive responses with USMS pages.
"""

import httpx
import lxml.html

from usms.core.async_auth import AsyncUSMSAuth
from usms.utils.logging_config import logger


class AsyncUSMSClient(httpx.AsyncClient):
    """Custom Async HTTP client for interacting with USMS."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    def __init__(self, username: str, password: str, timeout: float = 30.0) -> None:
        """Initialize a USMSClient instance."""
        super().__init__(
            auth=AsyncUSMSAuth(username, password),
            base_url=self.BASE_URL,
            http2=True,
            timeout=timeout,
            event_hooks={"response": [self._update_asp_state]},
        )
        self._asp_state = {}

    async def post(self, url: str, data: dict | None = None) -> httpx.Response:
        """Send a POST request with ASP.NET hidden fields included."""
        if data is None:
            data = {}

        # Merge stored ASP state with request data
        if self._asp_state and data:
            for asp_key, asp_value in self._asp_state.items():
                if not data.get(asp_key):
                    data[asp_key] = asp_value

        return await super().post(url=url, data=data)

    async def _update_asp_state(self, response: httpx.Response) -> None:
        """Extract ASP.NET hidden fields from responses to maintain session state."""
        try:
            response_html = lxml.html.fromstring(await response.aread())

            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                if hidden_input.value:
                    self._asp_state[hidden_input.name] = hidden_input.value
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse ASP.NET state: {e}")
