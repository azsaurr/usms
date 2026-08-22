"""Test client ownership and HTTP error handling."""

import pytest

from usms.core.client import HTTP_ERROR_STATUS, USMSClient
from usms.exceptions.errors import USMSPageResponseError


class _FakeClient:
    """A minimal stand-in for an httpx client."""

    def __init__(self) -> None:
        self.follow_redirects = False
        self.is_closed = False

    def get(self, url: str, **kwargs: object) -> None:
        """Present a sync `get` so the client is detected as synchronous."""

    def post(self, url: str, **kwargs: object) -> None:
        """Present a sync `post`."""

    def close(self) -> None:
        """Record that the client was closed."""
        self.is_closed = True


class _FakeResponse:
    """A response carrying only the status code the client inspects."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _client(*, owns_client: bool) -> tuple[USMSClient, _FakeClient]:
    """Return a USMSClient wrapping a fake client."""
    fake = _FakeClient()
    return USMSClient("user", "pass", fake, owns_client=owns_client), fake


def test_close_closes_a_client_we_created() -> None:
    """Test that a client the library created is closed on request."""
    client, fake = _client(owns_client=True)

    client.close()

    assert fake.is_closed


def test_close_leaves_a_caller_supplied_client_alone() -> None:
    """
    Test that a client handed to us is never closed.

    Home Assistant passes in a shared client; closing it would break unrelated
    integrations, so ownership has to be tracked rather than assumed.
    """
    client, fake = _client(owns_client=False)

    client.close()

    assert not fake.is_closed


def test_ownership_defaults_to_not_owned() -> None:
    """Test that a client is only ever closed when ownership was stated explicitly."""
    fake = _FakeClient()

    USMSClient("user", "pass", fake).close()

    assert not fake.is_closed


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 503])
def test_http_errors_raise(status) -> None:
    """
    Test that an HTTP error raises rather than being parsed as a page.

    An error page parses to no rows, so without this the caller is told there is
    no consumption data for the date rather than that the request failed.
    """
    with pytest.raises(USMSPageResponseError):
        USMSClient._raise_for_status(_FakeResponse(status), "https://example.test")  # noqa: SLF001


@pytest.mark.parametrize("status", [200, 302, HTTP_ERROR_STATUS - 1])
def test_non_error_statuses_pass(status) -> None:
    """Test that ordinary responses, including redirects, are left alone."""
    USMSClient._raise_for_status(_FakeResponse(status), "https://example.test")  # noqa: SLF001
