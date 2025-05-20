"""State Manager Module for USMS Client."""

from usms.parsers.asp_state_parser import ASPStateParser


class USMSClientASPStateMixin:
    """Mixin to manage ASP.NET hidden field state."""

    _asp_state: dict[str, str]

    def __init__(self) -> None:
        self._asp_state = {}

    def _extract_asp_state(self, response_content: bytes) -> None:
        """Extract ASP.NET hidden fields to maintain session state."""
        self._asp_state = ASPStateParser.parse(response_content)

    def _inject_asp_state(self, data: dict[str, str] | None = None) -> None:
        """Merge stored ASP state with request data."""
        if data is None:
            data = {}

        for key, value in self._asp_state.items():
            if key not in data:
                data[key] = value

        return data
