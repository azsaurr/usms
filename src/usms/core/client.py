"""
USMS Client Module.

Defines the clients used to talk to USMS. `USMSClient` is synchronous and
`AsyncUSMSClient` is asynchronous; both derive from `BaseUSMSClient`, which holds
everything that does not touch the network.

The two are separate classes rather than one class branching on a flag, following
the same split httpx uses for `Client` and `AsyncClient`. A single dual-mode class
has to sniff `inspect.iscoroutinefunction` at runtime and return "a response, or a
coroutine yielding one", which no type checker can follow and no reader can rely on.
"""

import asyncio
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from usms.core.auth import MAX_CAPTCHA_ATTEMPTS, MAX_CAPTCHA_FETCHES, USMSAuthMixin
from usms.core.state_manager import USMSClientASPStateMixin
from usms.exceptions.errors import USMSCaptchaError, USMSLoginError, USMSPageResponseError
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from usms.captcha import CaptchaSolver
    from usms.core.protocols import HTTPXClientProtocol, HTTPXResponseProtocol

# How many times a request is retried behind a re-authentication before giving up.
MAX_AUTH_ATTEMPTS = 3

# Multiplied by the attempt number, so retries space out instead of hammering USMS.
REAUTH_BACKOFF = timedelta(seconds=1)

# Status codes at or above this are treated as a failed request.
HTTP_ERROR_STATUS = 400

EXPIRED_SESSION_MESSAGE = (
    f"Session still expired after {MAX_AUTH_ATTEMPTS} re-authentication attempts. "
    "USMS allows only one active session per account, so another client may be "
    "logging in and invalidating this session."
)


class BaseUSMSClient(USMSClientASPStateMixin, USMSAuthMixin):
    """Everything the sync and async USMS clients share, minus the I/O."""

    BASE_URL = "https://www.usms.com.bn/SmartMeter/"

    #: Overridden by each concrete client so callers can tell them apart.
    async_mode: bool = False

    def __init__(
        self,
        username: str,
        password: str,
        client: "HTTPXClientProtocol",
        *,
        owns_client: bool = False,
        captcha_solver: "CaptchaSolver | None" = None,
    ) -> None:
        """
        Initialize USMS Client.

        `owns_client` records whether this client was created for us and may
        therefore be closed on our behalf. It stays False for a caller-supplied
        client - Home Assistant, for one, hands over a shared client that would
        break the rest of the application if we closed it.

        `captcha_solver` replaces the built-in model that reads the login captcha.
        """
        USMSAuthMixin.__init__(
            self, username=username, password=password, captcha_solver=captcha_solver
        )
        USMSClientASPStateMixin.__init__(self)

        client.follow_redirects = True

        self.client = client
        self._owns_client = owns_client

    def _build_url(self, url: str) -> str:
        """Return an absolute USMS URL for a path, leaving absolute URLs alone."""
        if url.startswith("http"):
            return url
        return f"{self.BASE_URL}{url}"

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

    @property
    def username(self) -> str:
        """Account username."""
        return self._username

    @property
    def password(self) -> str:
        """Account password."""
        return self._password


class USMSClient(BaseUSMSClient):
    """Synchronous USMS client."""

    async_mode = False

    def get(self, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a GET request."""
        return self._request("get", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a POST request, injecting the stored ASP.NET state."""
        kwargs["data"] = self._inject_asp_state(kwargs.get("data", {}))
        return self._request("post", url, **kwargs)

    def _request(self, http_method: str, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a request, re-authenticating and retrying if the session has expired."""
        url = self._build_url(url)
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
        self._extract_asp_state(response.read())

        return response

    def is_expired(self, response: "HTTPXResponseProtocol") -> bool:
        """Return True if the session behind this response is no longer valid."""
        return self._is_expired_response(
            response.status_code,
            response.read().decode("utf-8"),
        )

    def authenticate(self) -> None:
        """Run the USMS login flow."""
        logger.debug("Executing authentication flow...")

        # Retrieve the login page, and with it the ASP state the form needs.
        response = self.client.get(url=self.LOGIN_URL)
        payload = self._build_login_payload(response.read())

        # Submit the credentials; USMS checks them before asking for a captcha.
        response = self.client.post(url=self.LOGIN_URL, data=payload)
        self._raise_for_login_error(response.read())

        if self._is_captcha_challenge(response):
            response = self._answer_captcha(response)

        # A login ends in a redirect through LoginSession carrying the Sig token,
        # which the client has already followed into an authenticated session.
        self._resolve_sig(response)
        self._adopt_session_cookie()
        logger.debug("Authentication flow complete")

    def _answer_captcha(self, page: "HTTPXResponseProtocol") -> "HTTPXResponseProtocol":
        """Solve and submit the captcha on `page`, retrying with fresh ones."""
        for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
            page, answer = self._read_captcha(page)
            response = self.client.post(
                url=str(page.url), data=self._build_login_payload(page.read(), answer)
            )
            if not self._is_captcha_challenge(response):
                return response
            logger.debug("Captcha answer rejected (attempt %s)", attempt)
            page = response
        raise USMSCaptchaError

    def _read_captcha(self, page: "HTTPXResponseProtocol") -> tuple["HTTPXResponseProtocol", str]:
        """Return a captcha page and the solver's answer, once it is a plausible one."""
        for _ in range(MAX_CAPTCHA_FETCHES):
            image = self.client.get(url=self._captcha_image_url(page.read())).read()
            answer = self._captcha_solver(image)
            if self._is_plausible_captcha(answer):
                return page, answer
            # Reloading the page issues a new captcha; the old one is never submitted.
            page = self.client.get(url=str(page.url))
        raise USMSCaptchaError

    def close(self) -> None:
        """Close the underlying client, if this instance created it."""
        if self._owns_client:
            self.client.close()


class AsyncUSMSClient(BaseUSMSClient):
    """Asynchronous USMS client."""

    async_mode = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the async client and its re-authentication lock."""
        super().__init__(*args, **kwargs)

        # Serialises re-authentication so concurrent callers cannot invalidate each
        # other's session. Safe to build without a running loop since Python 3.10.
        self._reauth_lock = asyncio.Lock()

    async def get(self, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a GET request."""
        return await self._request("get", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a POST request, injecting the stored ASP.NET state."""
        kwargs["data"] = self._inject_asp_state(kwargs.get("data", {}))
        return await self._request("post", url, **kwargs)

    async def _request(self, http_method: str, url: str, **kwargs: Any) -> "HTTPXResponseProtocol":
        """Send a request, re-authenticating and retrying if the session has expired."""
        url = self._build_url(url)
        request_method = getattr(self.client, http_method.lower())

        for attempt in range(MAX_AUTH_ATTEMPTS):
            response = await request_method(url, **kwargs)
            if not await self.is_expired(response):
                break

            # USMS permits a single session per account, so concurrent callers must
            # not re-authenticate at once or each login invalidates the last.
            async with self._reauth_lock:
                if attempt:
                    await asyncio.sleep(REAUTH_BACKOFF.total_seconds() * attempt)
                await self.authenticate()
        else:
            # Returning here would hand the caller a login page dressed up as data.
            raise USMSLoginError(EXPIRED_SESSION_MESSAGE)

        self._raise_for_status(response, url)
        self._extract_asp_state(await response.aread())

        return response

    async def is_expired(self, response: "HTTPXResponseProtocol") -> bool:
        """Return True if the session behind this response is no longer valid."""
        return self._is_expired_response(
            response.status_code,
            (await response.aread()).decode("utf-8"),
        )

    async def authenticate(self) -> None:
        """Run the USMS login flow."""
        logger.debug("Executing authentication flow...")

        # Retrieve the login page, and with it the ASP state the form needs.
        response = await self.client.get(url=self.LOGIN_URL)
        payload = self._build_login_payload(await response.aread())

        # Submit the credentials; USMS checks them before asking for a captcha.
        response = await self.client.post(url=self.LOGIN_URL, data=payload)
        self._raise_for_login_error(await response.aread())

        if self._is_captcha_challenge(response):
            response = await self._answer_captcha(response)

        # A login ends in a redirect through LoginSession carrying the Sig token,
        # which the client has already followed into an authenticated session.
        self._resolve_sig(response)
        self._adopt_session_cookie()
        logger.debug("Authentication flow complete")

    async def _answer_captcha(self, page: "HTTPXResponseProtocol") -> "HTTPXResponseProtocol":
        """Solve and submit the captcha on `page`, retrying with fresh ones."""
        for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
            page, answer = await self._read_captcha(page)
            response = await self.client.post(
                url=str(page.url), data=self._build_login_payload(await page.aread(), answer)
            )
            if not self._is_captcha_challenge(response):
                return response
            logger.debug("Captcha answer rejected (attempt %s)", attempt)
            page = response
        raise USMSCaptchaError

    async def _read_captcha(
        self, page: "HTTPXResponseProtocol"
    ) -> tuple["HTTPXResponseProtocol", str]:
        """Return a captcha page and the solver's answer, once it is a plausible one."""
        for _ in range(MAX_CAPTCHA_FETCHES):
            image = await self.client.get(url=self._captcha_image_url(await page.aread()))
            # Solving is CPU-bound for up to a second or so; keep it off the event loop.
            answer = await asyncio.to_thread(self._captcha_solver, await image.aread())
            if self._is_plausible_captcha(answer):
                return page, answer
            # Reloading the page issues a new captcha; the old one is never submitted.
            page = await self.client.get(url=str(page.url))
        raise USMSCaptchaError

    async def aclose(self) -> None:
        """Close the underlying client, if this instance created it."""
        if self._owns_client:
            await self.client.aclose()
