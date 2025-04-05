"""
USMS Meter Tariff Module.

This module defines the USMSTariff class,
which represents the different tariff tiers
for a smart meter in the USMS system.
It provides methods to calculate meter charges,
and get current tier.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class USMSTariffTier:
    """Represents a tariff tier for USMS meter."""

    lower_bound: int
    upper_bound: int | float  # can be None for an open-ended range
    rate: float


@dataclass(frozen=True)
class USMSTariff:
    """Represents a tariff and its tiers for USMS meter."""

    tiers: list[USMSTariffTier]

    def calculate_cost(self, consumption: float) -> float:
        """Calculate the cost for given unit consumption, according to the tariff."""
        cost = 0.0

        for tier in self.tiers:
            bound_range = tier.upper_bound - tier.lower_bound + 1

            if consumption <= bound_range:
                cost += consumption * tier.rate
                break

            consumption -= bound_range
            cost += bound_range * tier.rate

        return round(cost, 2)

    def calculate_unit(self, cost: float) -> float:
        """Calculate the unit received for the cost paid, according to the tariff."""
        unit = 0.0

        for tier in self.tiers:
            bound_range = tier.upper_bound - tier.lower_bound + 1
            bound_cost = bound_range * tier.rate

            if cost <= bound_cost:
                unit += cost / tier.rate
                break

            cost -= bound_cost
            unit += bound_range

        return round(unit, 2)
