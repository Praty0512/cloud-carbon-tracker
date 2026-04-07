"""Simulation engine for cost vs carbon analysis."""

from config import SCENARIO_REGIONS, get_region_cost, get_region_intensity, get_region_label
from engine.carbon_engine import calculate_energy


def simulate(vm, storage, network):
    """Simulate carbon and cost for each region."""
    energy, _, _, _ = calculate_energy(vm, storage, network)

    results = []

    for region in SCENARIO_REGIONS:
        carbon = energy * get_region_intensity(region)
        cost = vm * get_region_cost(region)

        results.append({
            "Region": get_region_label(region),
            "Region Key": region,
            "Carbon": round(carbon, 2),
            "Cost": cost
        })

    return results
