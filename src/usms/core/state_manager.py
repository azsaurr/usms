"""State Manager Module for USMS Client."""

import lxml.html

from usms.utils.logging_config import logger


class USMSASPStateMixin:
    """Mixin to manage ASP.NET hidden field state."""

    _asp_state: dict[str, str]

    def __init__(self) -> None:
        self._asp_state = {}

    def _extract_asp_state(self, response_content: bytes) -> None:
        """Extract ASP.NET hidden fields to maintain session state."""
        try:
            response_html = lxml.html.fromstring(response_content)
            for hidden_input in response_html.findall(""".//input[@type="hidden"]"""):
                if hidden_input.value:
                    self._asp_state[hidden_input.name] = hidden_input.value
        except Exception as error:  # noqa: BLE001
            logger.error(f"Failed to parse ASP.NET state: {error}")

    def _inject_asp_state(self, data: dict[str, str] | None = None) -> dict[str, str]:
        """Merge stored ASP state with request data."""
        if data is None:
            data = {}

        for key, value in self._asp_state.items():
            if key not in data:
                data[key] = value

        return data
