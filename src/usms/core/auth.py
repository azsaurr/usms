"""
USMS Auth Module.

This module defines authentication class
customized especially for authenticating
with USMS accounts.
"""

from collections.abc import Generator

import httpx
import lxml.html

from usms.exceptions.errors import USMSLoginError
from usms.utils.logging_config import logger


class USMSAuth(httpx.Auth):
    """Custom implementation of authentication for USMS."""

    requires_response_body = True

    LOGIN_URL = "https://www.usms.com.bn/SmartMeter/ResLogin"
    SESSION_URL = "https://www.usms.com.bn/SmartMeter/LoginSession.aspx"

    def __init__(self, username: str, password: str) -> None:
        """Initialize a USMSAuth instance."""
        self._username = username
        self._password = password

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        """Handle authentication and session renewal."""
        response = yield request

        if self.is_expired(response):
            logger.debug("Executing authentication flow...")

            # First login request to get hidden ASP state
            response = yield httpx.Request(
                method="POST",
                url=self.LOGIN_URL,
            )
            response_html = lxml.html.fromstring(response.content)

            # Extract ASP.NET hidden fields
            asp_state = {}
            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                asp_state[hidden_input.name] = hidden_input.value
            asp_state["ASPxRoundPanel1$btnLogin"] = "Login"
            asp_state["ASPxRoundPanel1$txtUsername"] = self._username
            asp_state["ASPxRoundPanel1$txtPassword"] = self._password

            # Perform login with credentials
            response = yield httpx.Request(
                method="POST",
                url=self.LOGIN_URL,
                data=asp_state,
            )

            # Handle authentication errors
            response_html = lxml.html.fromstring(response.content)
            error_message = response_html.find(""".//*[@id="pcErr_lblErrMsg"]""")
            if error_message is not None:
                logger.error(error_message.text_content())
                raise USMSLoginError(error_message.text_content())

            # Extract session info from cookies
            request.cookies = response.cookies
            session_id = request.cookies["ASP.NET_SessionId"]
            request.headers["cookie"] = f"ASP.NET_SessionId={session_id}"

            # Extract authentication signature from redirect URL
            sig = response.headers["location"].split("Sig=")[-1].split("&")[-1]
            response = yield httpx.Request(
                method="GET",
                url=f"https://www.usms.com.bn/SmartMeter/LoginSession.aspx?pLoginName={self._username}&Sig={sig}",
                cookies=request.cookies,
            )

            response = yield response.next_request
            response = yield response.next_request
            logger.debug("Authentication flow complete")

            yield request

    def is_expired(self, response: httpx.Response) -> bool:
        """Check if the session has expired based on response content."""
        if response.status_code == 302 and "SessionExpire" in response.text:  # noqa: PLR2004
            logger.debug("Not logged in")
            return True
        if (
            response.status_code == 200  # noqa: PLR2004
            and "Your Session Has Expired, Please Login Again." in response.text
        ):
            logger.debug("Session has expired")
            return True
        return False
