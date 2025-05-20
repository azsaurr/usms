"""Meter Information Parser Module."""

from html.parser import HTMLParser
from typing import ClassVar


class MeterInfoParser(HTMLParser):
    """Meter Information Parser Module."""

    ID_FIELD_MAP: ClassVar[dict[str, str]] = {
        "2": "no",
        "5": "status",
        "6": "address",
        "7": "kampong",
        "8": "mukim",
        "9": "district",
        "10": "postcode",
        "11": "remaining_unit",
        "12": "remaining_credit",
        "17": "last_update",
    }
    data: dict[str, str]

    def __init__(self):
        """Initialize instance of MeterInfoParser."""
        super().__init__()
        self.data = dict.fromkeys(self.ID_FIELD_MAP.values())

        self._current_field = None
        self._capture_field = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        if tag == "td":
            for attr, value in attrs:
                if attr == "id" and value.startswith("ASPxCardView1_DXCardLayout"):
                    suffix = value.split("_")[-1]
                    self._current_field = self.ID_FIELD_MAP.get(suffix)
                elif attr == "class" and "dxflNestedControlCell" in value and self._current_field:
                    self._capture_field = True

    def handle_endtag(self, tag: str) -> None:
        """Handle the end of an HTML tag."""
        if tag == "td" and self._capture_field:
            self._current_field = None
            self._capture_field = False

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._capture_field and self._current_field:
            self.data[self._current_field] = data.strip()

            self._current_field = None
            self._capture_field = False

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extracts meter info."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
