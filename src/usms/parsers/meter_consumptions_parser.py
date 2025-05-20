"""Meter Consumptions Parser Module."""

from html.parser import HTMLParser


class MeterConsumptionsParser(HTMLParser):
    """Meter Consumptions Parser Module."""

    data: dict[str, str]

    def __init__(self) -> None:
        """Initialize instance of MeterConsumptionsParser."""
        super().__init__()
        self.data = {}
        self.test = []

        self._capture_start = False
        self._capture_end = False

        self._current_field = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        if tag == "tr":
            for attr, value in attrs:
                if attr == "id" and value.startswith("ASPxPageControl1_grid_DXDataRow"):
                    self._current_field = value[31:]
                    self._capture_start = True

    def handle_endtag(self, tag: str) -> None:
        """Handle the end of an HTML tag."""
        if self._capture_start:
            self._capture_end = True

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._capture_start and self._capture_end:
            self.data[self._current_field] = data.strip()

            self._capture_start = False
            self._capture_end = False
            self._current_field = ""

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extracts error message."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
