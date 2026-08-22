"""Meter Payment Information Parser Module."""

from html.parser import HTMLParser
from typing import ClassVar


class MeterPaymentInfoParser(HTMLParser):
    """
    Parses the debt and balance details from a meter's Top Up page.

    NB: USMS's element ids do not match the labels they are displayed under. The field
    shown as "Total Debt Owing" carries the id `lblDebtBalRemaining`, while the one
    shown as "Debt Balance Remaining" carries `lblOutstandingBalance`. The mapping
    below follows the *displayed* labels, which are the meaningful ones.
    """

    ID_FIELD_MAP: ClassVar[dict[str, str]] = {
        "pcAccount_lblCustType": "customer_type",
        "pcAccount_lblDebtCleranceModel": "debt_clearance_model",
        "pcAccount_lblDebtBalRemaining": "total_debt_owing",
        "pcAccount_lblRepaymentPeriod": "debt_repayment_period",
        "pcAccount_lblMonthlyDebtAmt": "monthly_debt_amount",
        "pcAccount_lblDebtRemainingPeriod": "debt_period_remaining",
        "pcAccount_lblOutstandingBalance": "debt_balance_remaining",
        "pcAccount_lblRemainingUnit": "remaining_unit",
        "pcAccount_lblCurrentBalance": "remaining_credit",
    }
    data: dict[str, str]

    def __init__(self) -> None:
        """Initialize instance of MeterPaymentInfoParser."""
        super().__init__()
        self.data = dict.fromkeys(self.ID_FIELD_MAP.values())

        self._current_field = None
        self._span_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Handle the start of an HTML tag."""
        if tag != "span":
            return

        # Values are wrapped in a nested <font>, so track depth to find the right close.
        if self._current_field is not None:
            self._span_depth += 1
            return

        for attr, value in attrs:
            if attr == "id" and value in self.ID_FIELD_MAP:
                self._current_field = self.ID_FIELD_MAP[value]
                self._span_depth = 1
                self.data[self._current_field] = ""
                break

    def handle_endtag(self, tag: str) -> None:
        """Handle the end of an HTML tag."""
        if tag == "span" and self._current_field is not None:
            self._span_depth -= 1
            if self._span_depth == 0:
                self.data[self._current_field] = self.data[self._current_field].strip()
                self._current_field = None

    def handle_data(self, data: str) -> None:
        """Handle the text data within an HTML tag."""
        if self._current_field is not None:
            self.data[self._current_field] += data

    @classmethod
    def parse(cls, html_response: bytes | str) -> dict[str, str]:
        """Parse the provided HTML response and extract the meter's payment info."""
        parser = cls()
        parser.feed(
            html_response.decode("utf-8") if isinstance(html_response, bytes) else html_response
        )
        return parser.data
