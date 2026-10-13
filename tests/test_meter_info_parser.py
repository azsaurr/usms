"""Test meter card parsing against USMS's October 2026 layout."""

from usms.parsers.account_info_parser import AccountInfoParser
from usms.parsers.meter_info_parser import MeterInfoParser

ITEM = (
    '<td id="ASPxCardView1_DXCardLayout0_{n}" class="dxflHACSys dxflGroupCell">'
    '<table class="dxflItem"><tr>'
    '<td class="dxflCaptionCell"><span id="ASPxCardView1_DXCardLayout0_{n}_Cap" '
    'class="dxDefaultCursor dxflCaption">{caption}</span></td>'
    '<td class="dxflNestedControlCell">{value}</td>'
    "</tr></table></td>"
)

# Cell numbers as USMS served them in October 2026, after "Full Name" was added and
# every later id moved up by one. Values are made up.
CARD = (
    '<table><tr><td class="dxcvCard"><table>'
    + "".join(
        "<tr>" + ITEM.format(n=n, caption=caption, value=value) + "</tr>"
        for n, caption, value in [
            (2, "Meter No:", "12345678"),
            (4, "Full Name:", "A N OTHER"),
            (5, "Meter Status:", "ACTIVE"),
            (6, "Address:", "NO 1 SPG 2"),
            (10, "Postcode:", "BA1111"),
            (12, "Remaining Unit:", "1,973.568 kWh"),
            (13, "Remaining Balance:", "$174.28"),
            (18, "Last Updated:", "13/10/2026"),
        ]
    )
    + "</table></td></tr></table>"
)


def test_fields_are_found_by_caption_not_cell_number() -> None:
    """Test that the shifted layout still maps every field to its value."""
    data = MeterInfoParser.parse(CARD)

    assert data["no"] == "12345678"
    assert data["status"] == "ACTIVE"
    assert data["postcode"] == "BA1111"
    assert data["remaining_unit"] == "1,973.568 kWh"
    assert data["remaining_credit"] == "$174.28"
    assert data["last_update"] == "13/10/2026"


def test_unknown_captions_are_ignored() -> None:
    """Test that a caption the parser does not know captures nothing."""
    data = MeterInfoParser.parse(CARD)

    assert "A N OTHER" not in data.values()


def test_account_page_yields_each_meter_card() -> None:
    """Test that the account parser hands each card to the meter parser intact."""
    meters = AccountInfoParser.parse(CARD + CARD.replace("12345678", "87654321"))["meters"]

    assert [meter["no"] for meter in meters] == ["12345678", "87654321"]
    assert all(meter["remaining_unit"] == "1,973.568 kWh" for meter in meters)
