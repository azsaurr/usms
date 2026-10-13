"""
Test the USMS login flow, captcha step included.

A scripted stand-in for USMS sits behind `httpx.MockTransport`, so redirects,
cookies and both clients are exercised for real. It reproduces the flow recorded
from a browser in October 2026: credentials are checked first and answered with a
redirect to `ResLogin?sc=...`, whose captcha must then be submitted to that URL.
"""

import asyncio
import re

import httpx
import pytest

from usms.core.auth import CAPTCHA_FIELD, MAX_CAPTCHA_ATTEMPTS, MAX_CAPTCHA_FETCHES, USMSAuthMixin
from usms.core.client import AsyncUSMSClient, USMSClient
from usms.exceptions.errors import USMSCaptchaError, USMSLoginError

USERNAME, PASSWORD = "00000001", "correct-horse"
SC = "c2NyaXB0ZWQ"
SIG = "c2lnbmVk"

LOGIN_PAGE = """<html><body><form method="post" action="./ResLogin{query}" id="form1">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="state-{serial}" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="validation" />
<img id="ASPxRoundPanel1_ASPxCaptcha1_IMG" src="/SmartMeter/DXB.axd?{image_query}DXCache={serial}" alt="Captcha image" />
<input name="ASPxRoundPanel1$ASPxCaptcha1$TB" type="text" />
{error}
</form></body></html>"""

ERROR_POPUP = '<span id="pcErr_lblErrMsg">Incorrect user name and password.</span>'


class FakeUSMS:
    """USMS's login endpoints, with a new captcha answer for every page served."""

    def __init__(self) -> None:
        self.serial = 0
        self.captcha_posts: list[str] = []
        self.images_served = 0

    def page(self, *, challenge: bool, error: str = "") -> httpx.Response:
        """Serve a login page carrying a fresh captcha."""
        self.serial += 1
        body = LOGIN_PAGE.format(
            query=f"?sc={SC}" if challenge else "",
            image_query=f"sc={SC}&amp;" if challenge else "",
            serial=self.serial,
            error=error,
        )
        return httpx.Response(
            200, text=body, headers={"set-cookie": "ASP.NET_SessionId=s1; path=/"}
        )

    @staticmethod
    def answer(serial: int) -> str:
        """Return the correct answer for the captcha on page `serial`."""
        return f"ans{serial:02d}"

    def handle(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        """Route a request the way USMS does."""
        path, query = request.url.path, dict(request.url.params)
        challenge = query.get("sc") == SC

        if path == "/SmartMeter/DXB.axd":
            self.images_served += 1
            return httpx.Response(200, content=f"image-{query['DXCache']}".encode())

        if path == "/SmartMeter/ResLogin" and request.method == "GET":
            return self.page(challenge=challenge)

        if path == "/SmartMeter/ResLogin" and request.method == "POST":
            form = dict(httpx.QueryParams(request.content.decode()))
            if (form["ASPxRoundPanel1$txtUsername"], form["ASPxRoundPanel1$txtPassword"]) != (
                USERNAME,
                PASSWORD,
            ):
                return self.page(challenge=challenge, error=ERROR_POPUP)
            back_to_challenge = httpx.Response(
                302, headers={"location": f"/SmartMeter/ResLogin?sc={SC}"}
            )
            if not challenge:
                return back_to_challenge
            self.captcha_posts.append(form[CAPTCHA_FIELD])
            if form[CAPTCHA_FIELD] != self.answer(int(form["__VIEWSTATE"].split("-")[1])):
                return back_to_challenge
            return httpx.Response(
                302,
                headers={
                    "location": f"/SmartMeter/LoginSession.aspx?pLoginName={USERNAME}&pType=R&Sig={SIG}",
                    "set-cookie": "ASP.NET_SessionId=authenticated; path=/",
                },
            )

        if path == "/SmartMeter/LoginSession.aspx":
            return httpx.Response(
                301, headers={"location": f"/SmartMeter/LoginSession?{request.url.query.decode()}"}
            )
        if path == "/SmartMeter/LoginSession":
            return httpx.Response(302, headers={"location": "/SmartMeter/MainPage"})
        if path == "/SmartMeter/MainPage":
            return httpx.Response(200, text="<html>MainPage</html>")
        return httpx.Response(404)


def scripted_solver(*wrong: str):
    """
    Return a solver giving each of `wrong` in turn, then the correct answers.

    The fake image carries its page serial, so the right answer is recoverable.
    """
    queue = list(wrong)
    calls: list[bytes] = []

    def solver(image: bytes) -> str:
        calls.append(image)
        if queue:
            return queue.pop(0)
        return FakeUSMS.answer(int(re.search(rb"image-(\d+)", image).group(1)))

    solver.calls = calls
    return solver


def sync_client(usms: FakeUSMS, solver, password: str = PASSWORD) -> USMSClient:
    """Return a USMSClient talking to `usms`."""
    transport = httpx.MockTransport(usms.handle)
    client = httpx.Client(transport=transport, base_url="https://www.usms.com.bn")
    return USMSClient(USERNAME, password, client, captcha_solver=solver)


def test_login_solves_the_captcha_on_the_challenge_page() -> None:
    """Test that the captcha is answered on the `sc` page and the session adopted."""
    usms, solver = FakeUSMS(), scripted_solver()
    client = sync_client(usms, solver)

    client.authenticate()

    assert usms.captcha_posts == [FakeUSMS.answer(2)]  # page 1 is the plain login form
    assert client.client.headers["cookie"] == "ASP.NET_SessionId=authenticated"


def test_implausible_guesses_fetch_a_new_captcha_instead_of_submitting() -> None:
    """Test that a guess of the wrong length is never submitted."""
    usms, solver = FakeUSMS(), scripted_solver("abc", "abcdefg")
    client = sync_client(usms, solver)

    client.authenticate()

    assert len(usms.captcha_posts) == 1
    assert len(solver.calls) == 3


def test_a_rejected_answer_is_retried_with_a_fresh_captcha() -> None:
    """Test that a wrong answer leads to another attempt rather than a failure."""
    usms, solver = FakeUSMS(), scripted_solver("wrong")
    client = sync_client(usms, solver)

    client.authenticate()

    assert usms.captcha_posts[0] == "wrong"
    assert len(usms.captcha_posts) == 2


def test_exhausted_captcha_attempts_raise_a_captcha_error() -> None:
    """
    Test that running out of answers raises USMSCaptchaError, not USMSLoginError.

    The credentials were accepted; reporting a login error would have callers - Home
    Assistant among them - ask the user to re-enter a password that is correct.
    """
    usms, solver = FakeUSMS(), scripted_solver(*["wrong"] * MAX_CAPTCHA_ATTEMPTS)
    client = sync_client(usms, solver)

    with pytest.raises(USMSCaptchaError) as caught:
        client.authenticate()

    assert not isinstance(caught.value, USMSLoginError)
    assert len(usms.captcha_posts) == MAX_CAPTCHA_ATTEMPTS


def test_a_solver_that_never_produces_a_plausible_guess_gives_up() -> None:
    """Test that image fetching is bounded, without ever submitting a guess."""
    usms, solver = FakeUSMS(), scripted_solver(*["x"] * MAX_CAPTCHA_FETCHES)
    client = sync_client(usms, solver)

    with pytest.raises(USMSCaptchaError):
        client.authenticate()

    assert usms.captcha_posts == []
    assert usms.images_served == MAX_CAPTCHA_FETCHES


def test_wrong_credentials_raise_before_any_captcha() -> None:
    """Test that a rejected password reports USMS's own message and skips the captcha."""
    usms, solver = FakeUSMS(), scripted_solver()
    client = sync_client(usms, solver, password="wrong")  # noqa: S106

    with pytest.raises(USMSLoginError, match="Incorrect user name and password"):
        client.authenticate()

    assert solver.calls == []


def test_async_login_solves_the_captcha() -> None:
    """Test the same flow through the async client."""
    usms, solver = FakeUSMS(), scripted_solver("wrong")

    async def run() -> AsyncUSMSClient:
        transport = httpx.MockTransport(usms.handle)
        async with httpx.AsyncClient(transport=transport) as http:
            client = AsyncUSMSClient(USERNAME, PASSWORD, http, captcha_solver=solver)
            await client.authenticate()
            return client

    client = asyncio.run(run())

    assert usms.captcha_posts == ["wrong", FakeUSMS.answer(3)]
    assert client.client.headers["cookie"] == "ASP.NET_SessionId=authenticated"


def test_captcha_image_url_is_unescaped_and_absolute() -> None:
    """Test that the HTML-escaped `&amp;` in the image URL is decoded."""
    page = b'<img id="ASPxRoundPanel1_ASPxCaptcha1_IMG" src="/SmartMeter/DXB.axd?sc=a&amp;DXCache=b" />'

    url = USMSAuthMixin._captcha_image_url(page)  # noqa: SLF001

    assert url == "https://www.usms.com.bn/SmartMeter/DXB.axd?sc=a&DXCache=b"


@pytest.mark.parametrize(
    ("guess", "plausible"),
    [("ab12c", True), ("ab12", False), ("ab12cd", False), ("ab 1c", False), ("", False)],
)
def test_plausible_captcha(guess, plausible) -> None:
    """Test that only five ASCII alphanumerics count as a possible answer."""
    assert USMSAuthMixin._is_plausible_captcha(guess) is plausible  # noqa: SLF001
