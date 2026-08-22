"""Test tariff calculations."""

import pytest

from usms.config.constants import TARIFFS

tolerance = 0.05
electric_tariff = TARIFFS["ELECTRIC"]
water_tariff = TARIFFS["WATER"]


@pytest.mark.parametrize(
    ("units", "expected_cost"),
    [
        # tier 1
        (0.0, 0.0),
        (1.0, 0.01),
        (123.0, 1.23),
        (420.0, 4.2),
        # tier 2
        (1387.5, 69.0),
        (1900.0, 110.0),
        # tier 3
        (3100.0, 228.0),
        # tier 4
        (4206.9, 342.83),
        (4855.75, 420.69),
        (5100.0, 450.0),
    ],
)
def test_electric_tariff_calculate_cost(units, expected_cost) -> None:
    """Test that cost can be calculated correctly according to the electricity consumption."""
    assert electric_tariff.calculate_cost(units) == pytest.approx(expected_cost, abs=tolerance)


@pytest.mark.parametrize(
    ("cost", "expected_units"),
    [
        # tier 1
        (0.0, 0.0),
        (0.01, 1.0),
        (1.23, 123.0),
        (4.2, 420.0),
        # tier 2
        (69.0, 1387.5),
        (110.0, 1900.0),
        # tier 3
        (228.0, 3100.0),
        # tier 4
        (342.83, 4206.9),
        (420.69, 4855.75),
        (450.0, 5100.0),
    ],
)
def test_electric_tariff_calculate_unit(cost, expected_units) -> None:
    """Test that unit can be calculated correctly according to the cost paid."""
    assert electric_tariff.calculate_unit(cost) == pytest.approx(expected_units, abs=tolerance)


@pytest.mark.parametrize(
    ("cost", "consumed_units", "expected_units"),
    [
        # Passing no consumption prices from the start of the tariff, which is the
        # historical behaviour and must not change.
        (69.0, 0.0, 1387.5),
        (110.0, 0.0, 1900.0),
        # Consumption that exactly fills tier 1 pushes pricing into tier 2.
        (112.0, 600.0, 1400.0),
        # Real reading, 2026-08-22: meter 55014488 held $76.22 credit having used
        # 2219.273 kWh, which lands in tier 3 at $0.10/kWh. The portal showed 762.228.
        (76.22, 2219.273, 762.2),
    ],
)
def test_electric_tariff_calculate_unit_from_consumption(cost, consumed_units, expected_units):
    """Test that units are priced from the tier the existing consumption reaches."""
    assert electric_tariff.calculate_unit(cost, consumed_units) == pytest.approx(
        expected_units, abs=tolerance
    )


def test_calculate_unit_accounts_for_crossing_into_a_dearer_tier() -> None:
    """
    Test that credit spanning a tier boundary is priced across both tiers.

    Real reading, 2026-08-22: meter 2402007817 held $25.14 having used 31.354 m3.
    Only 23.186 m3 remain in the $0.11 tier; the rest is charged at $0.44, four times
    dearer. The portal reported 228.625 m3, which is simply $25.14 at a flat $0.11 and
    ignores the boundary entirely.
    """
    # Priced from the current consumption, most of the credit falls in the $0.44 tier.
    assert water_tariff.calculate_unit(25.14, 31.354) == pytest.approx(74.53, abs=tolerance)
    # Priced from zero, the full 54.54 m3 of the cheap tier is available first.
    assert water_tariff.calculate_unit(25.14) == pytest.approx(98.04, abs=tolerance)


def test_water_tariff_calculate_cost_matches_published_tariff() -> None:
    """
    Test water cost against the published tariff: 54.54 m3 at $0.11, the rest at $0.44.

    The tier bounds encode a cancellation (54.54 - 1 + 1) that only holds while the
    first tier's lower bound is 1. Setting it to 0 would silently overcharge everyone.
    """
    assert water_tariff.calculate_cost(60.0) == pytest.approx(8.40, abs=tolerance)
    assert water_tariff.calculate_cost(54.54) == pytest.approx(6.00, abs=tolerance)
    assert water_tariff.calculate_cost(10.0) == pytest.approx(1.10, abs=tolerance)
