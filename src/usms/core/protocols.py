"""Protocol Definitions for USMS Client."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HTTPXResponseProtocol(Protocol):
    """HTTP Response Protocol for Dependency Injection."""

    def read(self) -> bytes:
        """Read and return the response content."""

    async def aread(self) -> bytes:
        """Read and return the response content."""

    @property
    def status_code(self) -> int:
        """Response status code."""

    @property
    def content(self) -> bytes:
        """Response content."""

    @property
    def text(self) -> str:
        """Response text."""

    @property
    def history(self) -> list["HTTPXResponseProtocol"]:
        """List of past responses."""

    @property
    def url(self) -> Any:
        """Returns the URL for which the request was made."""


@runtime_checkable
class HTTPXClientProtocol(Protocol):
    """HTTP Client Protocol for Dependency Injection."""

    def get(self, url: str, **kwargs: Any) -> HTTPXResponseProtocol:
        """Make a GET request."""

    def post(self, url: str, **kwargs: Any) -> HTTPXResponseProtocol:
        """Make a POST request."""

    @property
    def cookies(self) -> Any:
        """Cookie values to include when sending requests."""

    @cookies.setter
    def cookies(self, cookies: Any) -> None:
        """Cookie values to be set."""

    @property
    def headers(self) -> Any:
        """HTTP headers to include when sending requests."""

    @headers.setter
    def headers(self, headers: Any) -> None:
        """HTTP headers to be set."""

    @property
    def follow_redirects(self) -> Any:
        """HTTP follow_redirects config."""

    @follow_redirects.setter
    def follow_redirects(self, headers: Any) -> None:
        """HTTP follow_redirects config to be set."""
