"""
USMS Auth Module.

This module defines authentication class
customized especially for authenticating
with USMS accounts.
"""

from collections.abc import Callable

from usms.core.protocols import HTTPXResponseProtocol
from usms.exceptions.errors import USMSLoginError
from usms.utils.logging_config import logger


class USMSClientAuthMixin:
    """Custom implementation of authentication for USMS."""

    _username: str
    _password: str

    LOGIN_URL = "https://www.usms.com.bn/SmartMeter/ResLogin"
    SESSION_URL = "https://www.usms.com.bn/SmartMeter/LoginSession.aspx"

    def __init__(self, username: str, password: str, *args, **kwargs) -> None:
        """Initialize a USMSAuth instance."""
        self._username = username
        self._password = password

    def is_expired(self, response: HTTPXResponseProtocol) -> Callable:
        """Return authentication method for the client/session."""
        if self.async_mode:
            return self._is_expired_async(response)  # has to be awaited
        return self._is_expired_sync(response)

    def _is_expired_sync(self, response: HTTPXResponseProtocol) -> bool:
        """Return True if client/session is expired, based on given response."""
        response_content = response.read()
        response_text = response_content.decode("utf-8")

        if response.status_code == 302 and "SessionExpire" in response_text:  # noqa: PLR2004
            logger.debug("Not logged in")
            return True

        if (
            response.status_code == 200  # noqa: PLR2004
            and "Your Session Has Expired, Please Login Again." in response_text
        ):
            logger.debug("Session has expired")
            return True

        return False

    async def _is_expired_async(self, response: HTTPXResponseProtocol) -> bool:
        """Return True if client/session is expired, based on given response."""
        response_content = await response.aread()
        response_text = response_content.decode("utf-8")

        if response.status_code == 302 and "SessionExpire" in response_text:  # noqa: PLR2004
            logger.debug("Not logged in")
            return True

        if (
            response.status_code == 200  # noqa: PLR2004
            and "Your Session Has Expired, Please Login Again." in response_text
        ):
            logger.debug("Session has expired")
            return True

        return False

    def authenticate(self) -> Callable:
        """Return authentication method for the client/session."""
        if self.async_mode:
            return self._authenticate_async()  # has to be awaited
        return self._authenticate_sync()

    def _authenticate_sync(self) -> HTTPXResponseProtocol:
        logger.debug("Executing authentication flow...")

        # First login request to get hidden ASP state
        response = self.client.get(url=self.LOGIN_URL)
        response_content = response.read()
        asp_state = self._extract_asp_state(response_content)
        asp_state["ASPxRoundPanel1$btnLogin"] = "Login"
        asp_state["ASPxRoundPanel1$txtUsername"] = self._username
        asp_state["ASPxRoundPanel1$txtPassword"] = self._password

        # Perform login with credentials
        response = self.client.post(url=self.LOGIN_URL, data=asp_state)

        '''
        # Handle authentication errors
        response_html = lxml.html.fromstring(response.content)
        error_message = response_html.find(""".//*[@id="pcErr_lblErrMsg"]""")
        if error_message is not None:
            error_message = error_message.text_content()
            logger.error(error_message)
            raise USMSLoginError(error_message)
        '''

        # Extract session info from cookies
        session_id = self.client.cookies["ASP.NET_SessionId"]
        self.client.headers["cookie"] = f"ASP.NET_SessionId={session_id}"

        sig = None
        for past_response in response.history:
            past_response_url = str(past_response.url)
            if "Sig=" in past_response_url:
                sig = past_response_url.split("Sig=")[-1].split("&")[-1]
                break

        if sig is None:
            raise USMSLoginError

        response = self.client.get(
            url=f"https://www.usms.com.bn/SmartMeter/LoginSession.aspx?pLoginName={self._username}&Sig={sig}"
        )
        logger.debug("Authentication flow complete")

    async def _authenticate_async(self) -> HTTPXResponseProtocol:
        logger.debug("Executing authentication flow...")

        # First login request to get hidden ASP state
        response = await self.client.get(url=self.LOGIN_URL)
        response_content = await response.aread()
        asp_state = self._extract_asp_state(response_content)
        asp_state["ASPxRoundPanel1$btnLogin"] = "Login"
        asp_state["ASPxRoundPanel1$txtUsername"] = self._username
        asp_state["ASPxRoundPanel1$txtPassword"] = self._password

        # Perform login with credentials
        response = await self.client.post(url=self.LOGIN_URL, data=asp_state)

        '''
        # Handle authentication errors
        response_html = lxml.html.fromstring(response.content)
        error_message = response_html.find(""".//*[@id="pcErr_lblErrMsg"]""")
        if error_message is not None:
            error_message = error_message.text_content()
            logger.error(error_message)
            raise USMSLoginError(error_message)
        '''

        # Extract session info from cookies
        session_id = self.client.cookies["ASP.NET_SessionId"]
        self.client.headers["cookie"] = f"ASP.NET_SessionId={session_id}"

        sig = None
        for past_response in response.history:
            past_response_url = str(past_response.url)
            if "Sig=" in past_response_url:
                sig = past_response_url.split("Sig=")[-1].split("&")[-1]
                break

        if sig is None:
            raise USMSLoginError

        response = await self.client.get(
            url=f"https://www.usms.com.bn/SmartMeter/LoginSession.aspx?pLoginName={self._username}&Sig={sig}"
        )
        logger.debug("Authentication flow complete")
