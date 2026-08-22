"""Test parsing of the meter Top Up page."""

from dataclasses import dataclass
from datetime import datetime

import pytest

from usms.config.constants import BRUNEI_TZ
from usms.models.meter import USMSMeter
from usms.parsers.meter_payment_info_parser import MeterPaymentInfoParser
from usms.services.sync.meter import USMSMeter as SyncUSMSMeter
from usms.utils.helpers import parse_currency


def _span(element_id: str, value: str) -> str:
    """Return markup matching how USMS wraps a value, including the nested <font>."""
    return (
        f'<tr><td class="avenir">label</td><td>:</td>'
        f'<td><span class="dxeBase avenir" id="{element_id}">'
        f'<font color="#404041" size="3">{value}</font></span></td></tr>'
    )


# A meter carrying debt; the live account has none, so this covers the populated case.
PAGE_WITH_DEBT = (
    "<table>"
    + "".join(
        [
            _span("pcAccount_lblCustType", "Residential"),
            _span("pcAccount_lblMeterNo2", "55014488"),
            _span("pcAccount_lblDebtCleranceModel", "DEBT_ADJUSTED"),
            # NB: USMS shows this one as "Total Debt Owing" despite the id.
            _span("pcAccount_lblDebtBalRemaining", "$1,234.56"),
            _span("pcAccount_lblRepaymentPeriod", "12 months"),
            _span("pcAccount_lblMonthlyDebtAmt", "$102.88"),
            _span("pcAccount_lblDebtRemainingPeriod", "7"),
            # NB: USMS shows this one as "Debt Balance Remaining".
            _span("pcAccount_lblOutstandingBalance", "$720.16"),
            _span("pcAccount_lblRemainingUnit", "762.228 kWh"),
            _span("pcAccount_lblCurrentBalance", "$76.22"),
        ]
    )
    + "</table>"
)

# Matches the live account: no debt, with "not applicable" rendered as a dash/blank.
PAGE_WITHOUT_DEBT = (
    "<table>"
    + "".join(
        [
            _span("pcAccount_lblCustType", "Residential"),
            _span("pcAccount_lblDebtCleranceModel", "DEBT_ADJUSTED"),
            _span("pcAccount_lblDebtBalRemaining", "$0.00"),
            _span("pcAccount_lblRepaymentPeriod", "-"),
            _span("pcAccount_lblMonthlyDebtAmt", "$0.00"),
            _span("pcAccount_lblDebtRemainingPeriod", ""),
            _span("pcAccount_lblOutstandingBalance", "$0.00"),
        ]
    )
    + "</table>"
)


def _meter() -> USMSMeter:
    """Return a bare meter instance to apply parsed payment data to."""
    return USMSMeter.__new__(USMSMeter)


def test_parses_values_out_of_nested_font_tags() -> None:
    """Test that values wrapped in a nested <font> are captured, not the tags."""
    data = MeterPaymentInfoParser.parse(PAGE_WITH_DEBT)

    assert data["customer_type"] == "Residential"
    assert data["debt_clearance_model"] == "DEBT_ADJUSTED"
    assert data["total_debt_owing"] == "$1,234.56"
    assert data["remaining_unit"] == "762.228 kWh"


def test_meter_populated_from_payment_page_with_debt() -> None:
    """Test that debt fields land on the meter as numbers, thousands separator included."""
    meter = _meter()
    meter.update_from_payment_json(MeterPaymentInfoParser.parse(PAGE_WITH_DEBT))

    assert meter.customer_type == "Residential"
    assert meter.total_debt_owing == pytest.approx(1234.56)
    assert meter.monthly_debt_amount == pytest.approx(102.88)
    assert meter.debt_balance_remaining == pytest.approx(720.16)
    assert meter.debt_repayment_period == "12 months"
    assert meter.debt_period_remaining == "7"
    assert meter.has_debt is True


def test_meter_populated_from_payment_page_without_debt() -> None:
    """Test that a dash or blank period becomes None rather than a literal string."""
    meter = _meter()
    meter.update_from_payment_json(MeterPaymentInfoParser.parse(PAGE_WITHOUT_DEBT))

    assert meter.total_debt_owing == 0.0
    assert meter.debt_repayment_period is None
    assert meter.debt_period_remaining is None
    assert meter.has_debt is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("$0.00", 0.0),
        ("$76.22", 76.22),
        ("$1,234.56", 1234.56),
        ("-", 0.0),
        ("", 0.0),
        (None, 0.0),
        ("not a number", 0.0),
    ],
)
def test_parse_currency(value, expected) -> None:
    """Test that USMS currency strings parse, and non-values fall back to zero."""
    assert parse_currency(value) == pytest.approx(expected)


def test_topup_url_is_meter_specific() -> None:
    """Test that the top up URL carries the meter's base64 id."""
    meter = _meter()
    meter.id = "NTUwMTQ0ODg="

    assert meter.topup_url == (
        "https://www.usms.com.bn/SmartMeter/Payment/WebForm2?p=NTUwMTQ0ODg=&s=h"
    )


def test_debt_attributes_do_not_break_dataclass_subclassing() -> None:
    """
    Test that a subclass may still add fields without defaults.

    The debt attributes are intentionally unannotated. Annotating them would make
    them dataclass fields *with defaults*, and any subclass adding a field without
    one would then fail with "non-default argument follows default argument".
    ha_usms's HAUSMSMeterData does exactly that, so this guards against a change
    here silently breaking the integration at import time.
    """

    @dataclass
    class _Downstream(USMSMeter):
        last_refresh: datetime
        new_statistics: list
        currency: str = "BND"

    assert _Downstream is not None


def test_debt_defaults_available_before_fetch() -> None:
    """Test that debt attributes read sensibly before the Top Up page is fetched."""
    meter = _meter()

    assert meter.total_debt_owing == 0.0
    assert meter.customer_type is None
    assert meter.has_debt is False


def _cost_warning_for(customer_type: str, caplog) -> str:
    """Return whatever was logged while costing a meter of the given customer type."""
    meter = SyncUSMSMeter.__new__(SyncUSMSMeter)
    meter.no = "55014488"
    meter.type = "Electricity"
    meter.customer_type = customer_type
    consumptions = {datetime(2026, 8, 1, tzinfo=BRUNEI_TZ): 100.0}

    with caplog.at_level("WARNING", logger="usms"):
        meter.calculate_total_cost(consumptions)

    return caplog.text.lower()


def test_cost_warns_for_non_residential_meters(caplog) -> None:
    """
    Test that a commercial meter warns rather than returning a wrong cost silently.

    Only residential tariffs are defined; USMS bills commercial supplies per kVA of
    capacity, which these consumption tiers cannot express.
    """
    assert "residential" in _cost_warning_for("Commercial", caplog)


def test_cost_does_not_warn_for_residential_meters(caplog) -> None:
    """Test that the ordinary residential path stays quiet."""
    assert "residential" not in _cost_warning_for("Residential", caplog)
