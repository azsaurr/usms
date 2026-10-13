"""
USMS Auth Module.

Holds the parts of the USMS login flow that involve no I/O, so the sync and async
clients can share them and each implement only the request sequence itself. This
mirrors how httpx splits `Client` and `AsyncClient` over a common base: the
protocol lives in one place, the transport does not.
"""

import html
import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlparse

from usms.captcha import solve
from usms.exceptions.errors import USMSLoginError
from usms.parsers.asp_state_parser import ASPStateParser
from usms.parsers.error_message_parser import ErrorMessageParser
from usms.utils.logging_config import logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from usms.captcha import CaptchaSolver
    from usms.core.protocols import HTTPXClientProtocol, HTTPXResponseProtocol

# USMS answers an unauthenticated request with a redirect, and an expired one with a
# normal page carrying a notice, so both status codes have to be recognised.
HTTP_FOUND = 302
HTTP_OK = 200

SESSION_EXPIRED_NOTICE = "Your Session Has Expired, Please Login Again."

# Every USMS captcha is this long. A guess of any other length is certainly wrong, and
# fetching a fresh image costs nothing, whereas a wrong submission costs a round trip.
CAPTCHA_LENGTH = 5

# Captcha answers submitted per login, and images fetched per answer while looking
# for one of the right length, before the login is given up as unsolvable.
MAX_CAPTCHA_ATTEMPTS = 3
MAX_CAPTCHA_FETCHES = 10

CAPTCHA_FIELD = "ASPxRoundPanel1$ASPxCaptcha1$TB"
CAPTCHA_IMAGE_PATTERN = re.compile(rb'id="ASPxRoundPanel1_ASPxCaptcha1_IMG"\s+src="([^"]+)"')


class USMSAuthMixin:
    """The I/O-free half of the USMS login flow."""

    _username: str
    _password: str
    _captcha_solver: "CaptchaSolver"

    # Supplied by the concrete client that composes this mixin.
    client: "HTTPXClientProtocol"

    LOGIN_URL = "https://www.usms.com.bn/SmartMeter/ResLogin"

    def __init__(
        self,
        username: str,
        password: str,
        *args,
        captcha_solver: "CaptchaSolver | None" = None,
        **kwargs,
    ) -> None:
        """
        Store the credentials the login flow will submit.

        `captcha_solver` reads the captcha USMS asks for after accepting the
        credentials; it defaults to the built-in model in `usms.captcha`.
        """
        self._username = username
        self._password = password
        self._captcha_solver = captcha_solver or solve

    def _build_login_payload(self, login_page: bytes, captcha: str = "") -> dict[str, str]:
        """
        Return the login form payload, built from the login page's ASP state.

        The first submission leaves the captcha empty: USMS checks the credentials
        before the captcha, and only then serves the captcha page that will be
        accepted.
        """
        payload = ASPStateParser.parse(login_page)
        payload["ASPxRoundPanel1$btnLogin"] = "Login"
        payload["ASPxRoundPanel1$txtUsername"] = self._username
        payload["ASPxRoundPanel1$txtPassword"] = self._password
        payload[CAPTCHA_FIELD] = captcha
        return payload

    @staticmethod
    def _raise_for_login_error(response_content: bytes) -> None:
        """Raise if the login response carries an error message."""
        error_message = ErrorMessageParser.parse(response_content).get("error_message", "")
        if error_message:
            logger.error(error_message)
            raise USMSLoginError(error_message)

    def _adopt_session_cookie(self) -> None:
        """Pin the session id USMS just issued onto subsequent requests."""
        session_id = self.client.cookies["ASP.NET_SessionId"]
        self.client.headers["cookie"] = f"ASP.NET_SessionId={session_id}"

    @classmethod
    def _is_captcha_challenge(cls, response: "HTTPXResponseProtocol") -> bool:
        """
        Return True if a login response is the captcha page.

        Accepted credentials are answered with a redirect back to the login form,
        now carrying an `sc` query parameter, whose captcha is the one checked. A
        rejected captcha lands on the same page again.
        """
        if cls._extract_sig(response.history) is not None:
            return False
        return "sc" in parse_qs(urlparse(str(response.url)).query)

    @staticmethod
    def _captcha_image_url(page: bytes) -> str:
        """Return the absolute URL of the captcha image on a login page."""
        match = CAPTCHA_IMAGE_PATTERN.search(page)
        if match is None:
            msg = "The USMS captcha page has no captcha image."
            raise USMSLoginError(msg)
        return urljoin(USMSAuthMixin.LOGIN_URL, html.unescape(match.group(1).decode()))

    @staticmethod
    def _is_plausible_captcha(guess: str) -> bool:
        """Return True if a solver's guess could be a USMS captcha answer."""
        return len(guess) == CAPTCHA_LENGTH and guess.isascii() and guess.isalnum()

    @staticmethod
    def _extract_sig(history: "Iterable") -> str | None:
        """
        Return the `Sig` token USMS embeds in a redirect URL, or None if absent.

        Parsed as a query parameter rather than split out of the string: `Sig` is
        currently the last parameter, but splitting on the final `&` would silently
        return the wrong value the moment USMS appends anything after it.
        """
        for past_response in history:
            query = parse_qs(urlparse(str(past_response.url)).query)
            if "Sig" in query:
                return query["Sig"][0]
        return None

    def _resolve_sig(self, response: "HTTPXResponseProtocol") -> str:
        """Return the Sig token from a login response, or raise if it is missing."""
        sig = self._extract_sig(response.history)
        if sig is None:
            raise USMSLoginError
        return sig

    @staticmethod
    def _is_expired_response(status_code: int, response_text: str) -> bool:
        """Return True if the given response indicates the session is gone."""
        if status_code == HTTP_FOUND and "SessionExpire" in response_text:
            logger.debug("Not logged in")
            return True

        if status_code == HTTP_OK and SESSION_EXPIRED_NOTICE in response_text:
            logger.debug("Session has expired")
            return True

        return False
