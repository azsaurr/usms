"""ASP.net State Parser Module."""

from html.parser import HTMLParser


class ASPStateParser(HTMLParser):
    """Hidden ASP.net State Parser Module."""

    data: dict[str, str]

    def __init__(self) -> None:
        """Initialize instance of ASPStateParser."""
        super().__init__()
        self.data = {}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        if tag == "input":
            attr_dict = dict(attrs)
            if attr_dict.get("type") == "hidden" and "name" in attr_dict and "value" in attr_dict:
                self.data[attr_dict["name"]] = attr_dict["value"]

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extracts hidden ASP.net state."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
