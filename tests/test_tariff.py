# ruff: noqa: PLR2004
"""Test tariff calculations."""

import pytest

from usms.config.constants import TARIFFS

tolerance = 0.05
electric_tariff = TARIFFS["ELECTRIC"]


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
