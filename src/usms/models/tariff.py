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

    def calculate_unit(self, cost: float, consumed_units: float = 0.0) -> float:
        """
        Calculate the unit received for the cost paid, according to the tariff.

        Because the tariff is progressive, the units a given credit buys depend on how
        far into the tiers the meter already is. `consumed_units` is the consumption
        already accrued this billing period; tiers it has used up are skipped, so the
        credit is priced from the tier actually in effect.

        With the default of 0.0 this prices from the start of the tariff, i.e. what the
        credit would buy at the beginning of a billing period.

        Note this deliberately diverges from the USMS portal, which extrapolates at a
        flat current-tier rate and so overestimates once a credit would cross into a
        dearer tier.
        """
        unit = 0.0
        unbilled_units = consumed_units

        for tier in self.tiers:
            bound_range = tier.upper_bound - tier.lower_bound + 1

            # Skip over whatever portion of this tier the existing consumption used up.
            used_range = min(unbilled_units, bound_range)
            unbilled_units -= used_range
            available_range = bound_range - used_range
            if available_range <= 0:
                continue

            bound_cost = available_range * tier.rate
            if cost <= bound_cost:
                unit += cost / tier.rate
                break

            cost -= bound_cost
            unit += available_range

        return round(unit, 2)
