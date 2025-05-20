"""Error Message Parser Module."""

from html.parser import HTMLParser


class ErrorMessageParser(HTMLParser):
    """Error Message Parser Module."""

    data: dict[str, str]

    def __init__(self) -> None:
        """Initialize instance of ErrorMessageParser."""
        super().__init__()
        self.data = {
            "error_message": None,
        }
        self._capture = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        for attr, value in attrs:
            if attr == "id" and value == "pcErr_lblErrMsg":
                self._capture = True

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._capture:
            self.data["error_message"] = data.strip()
            self._capture = False

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extracts error message."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
