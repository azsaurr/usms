"""Protocol Definitions for USMS Client."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HTTPClient(Protocol):
    """HTTP Client Protocol for Dependency Injection."""

    def get(self, url: str, **kwargs: Any) -> Any:
        """Make a GET request."""

    def post(self, url: str, **kwargs: Any) -> Any:
        """Make a POST request."""
