"""Account Information Parser Module."""

from html.parser import HTMLParser

from usms.parsers.meter_info_parser import MeterInfoParser


class AccountInfoParser(HTMLParser):
    """Account Information Parser Module."""

    data: dict[str, str]

    def __init__(self):
        """Initialize instance of AccountInfoParser."""
        super().__init__()
        self.data = {
            "name": None,
            "meters": [],
        }
        self._capture_name_start = False
        self._capture_name_end = False

        self._capture_meter_td = False
        self._meter_td_buffer = ""

        self._td_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        if tag == "td":
            # nested td, traverse down
            if self._capture_meter_td:
                self._td_depth += 1

            for attr, value in attrs:
                # name element
                if attr == "id" and value == "ASPxCardView1_DXCardLayout0_4":
                    self._capture_name_start = True
                # start of meter card, td_depth = 0 (root)
                elif attr == "class" and value == "dxcvCard" and not self._capture_meter_td:
                    self._capture_meter_td = True
                    self._td_depth = 1
                    self._meter_td_buffer += self.get_starttag_text()

        if self._capture_meter_td:
            self._meter_td_buffer += self.get_starttag_text()

    def handle_endtag(self, tag: str) -> None:
        """Handle the end of an HTML tag."""
        if self._capture_name_start:
            self._capture_name_end = True

        if self._capture_meter_td:
            self._meter_td_buffer += f"</{tag}>"
            if tag == "td":
                # traverse up one td_depth
                self._td_depth -= 1

                # reached the root td element
                if self._td_depth == 0:
                    meter_data = MeterInfoParser.parse(self._meter_td_buffer)
                    self.data["meters"].append(meter_data)

                    # reset flag and buffer
                    self._capture_meter_td = False
                    self._meter_td_buffer = ""

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._capture_name_start and self._capture_name_end:
            self.data["name"] = data.strip()
            self._capture_name_start = False
            self._capture_name_end = False
        elif self._capture_meter_td:
            self._meter_td_buffer += data.strip()

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extracts account info."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
