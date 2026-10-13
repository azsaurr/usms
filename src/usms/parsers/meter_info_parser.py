"""Meter Information Parser Module."""

from html.parser import HTMLParser
from typing import ClassVar


class MeterInfoParser(HTMLParser):
    """
    Meter Information Parser Module.

    Fields are found by their caption ("Remaining Unit:") rather than by the numeric
    suffix of the card cell's id. USMS numbers those cells by position, so adding one
    field to the card - as it did in October 2026 - shifts every id after it and
    silently mismatches the rest.
    """

    CAPTION_FIELD_MAP: ClassVar[dict[str, str]] = {
        "Meter No": "no",
        "Meter Status": "status",
        "Address": "address",
        "Kampong": "kampong",
        "Mukim": "mukim",
        "District": "district",
        "Postcode": "postcode",
        "Remaining Unit": "remaining_unit",
        "Remaining Balance": "remaining_credit",
        "Remaining Credit": "remaining_credit",
        "Last Updated": "last_update",
    }
    data: dict[str, str]

    def __init__(self):
        """Initialize instance of MeterInfoParser."""
        super().__init__()
        self.data = dict.fromkeys(self.CAPTION_FIELD_MAP.values())

        self._in_caption = False
        self._current_field = None
        self._capture_field = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "span" and "dxflCaption" in classes:
            self._in_caption = True
        elif tag == "td" and "dxflNestedControlCell" in classes and self._current_field:
            self._capture_field = True

    def handle_endtag(self, tag: str) -> None:
        """Handle the end of an HTML tag."""
        if tag == "span":
            self._in_caption = False
        elif tag == "td" and self._capture_field:
            self._current_field = None
            self._capture_field = False

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._in_caption:
            self._current_field = self.CAPTION_FIELD_MAP.get(data.strip().rstrip(":").strip())
        elif self._capture_field and self._current_field:
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
