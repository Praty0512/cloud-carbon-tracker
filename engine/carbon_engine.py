"""Carbon emission calculation engine (manual calculator / legacy call sites).

Historically this module multiplied VM-hours, storage, and network by three
flat, made-up constants (``COMPUTE_FACTOR = 0.5``, etc.) regardless of which
cloud provider, instance size, or region was involved. It now delegates to
:mod:`engine.emission_factors`, the same Cloud Carbon Footprint (CCF)
methodology used by :mod:`engine.standardized_carbon_engine` for real
provider ingestion -- so the simple manual calculator and the multi-cloud
ingestion pipeline agree on the physics.

The function signatures below are unchanged on purpose: several views
(``carbon_calculator``, ``upload_analytics``, ``sustainability_scorecard``,
``carbon_forecast``) and the ``/api/carbon`` route call
``calculate_carbon(vm, storage, network, region)`` directly, so keeping the
signature stable means every one of those call sites gets more accurate,
sourced numbers with no other code changes required.

Modeling notes / simplifying assumptions (documented rather than hidden):
    * ``vm`` is treated as vCPU-hours for a single default vCPU at the
      hyperscale-average 50% utilization (see
      ``engine.emission_factors.DEFAULT_CPU_UTILIZATION``). Callers that
      know the real vCPU count and utilization should use
      :func:`engine.standardized_carbon_engine.calculate_standardized_emissions`
      instead.
    * ``storage`` (GB) is treated as an allocated-capacity snapshot held for
      one billing month (730 hours), consistent with how the calculator UI
      presents it, using CCF's SSD Watt-hour/TB-hour coefficient.
    * The manual calculator does not know which cloud provider a workload
      runs on, so it defaults to AWS's published PUE and CPU power curve.
      This is a labeled default, not a guess presented as fact -- see
      :func:`calculate_carbon_detailed` for the fully-attributed version.
"""

from __future__ import annotations

from config import get_region_intensity, resolve_region_key
from engine.emission_factors import (
    apply_pue,
    estimate_compute_energy_kwh,
    estimate_network_energy_kwh,
    estimate_storage_energy_kwh,
)

_DEFAULT_PROVIDER = "AWS"
_STORAGE_HOURS_ASSUMPTION = 730.0  # one billing month, see module docstring


def calculate_energy(vm, storage, network):
    """Calculate total energy consumption from cloud resources.

    Args:
        vm: Virtual machine hours (treated as 1-vCPU-hours)
        storage: Storage in GB (allocated capacity, monthly snapshot)
        network: Network transfer in GB

    Returns:
        Tuple: (total_energy, compute_energy, storage_energy, network_energy) in kWh
    """
    compute = estimate_compute_energy_kwh(_DEFAULT_PROVIDER, vcpu_count=1, hours=vm)
    storage_e = estimate_storage_energy_kwh(storage, hours=_STORAGE_HOURS_ASSUMPTION)
    network_e = estimate_network_energy_kwh(network)

    it_total = compute + storage_e + network_e
    total = apply_pue(it_total, _DEFAULT_PROVIDER)

    return total, compute, storage_e, network_e


def calculate_carbon(vm, storage, network, region):
    """Calculate carbon emissions from cloud usage.

    Args:
        vm: Virtual machine hours
        storage: Storage in GB
        network: Network transfer in GB
        region: Region or provider region string

    Returns:
        Tuple: (energy, carbon, compute, storage_energy, network_energy)
    """
    energy, compute, storage_e, network_e = calculate_energy(vm, storage, network)
    carbon = energy * get_region_intensity(region)

    return energy, carbon, compute, storage_e, network_e


def calculate_carbon_detailed(vm, storage, network, region, provider: str = _DEFAULT_PROVIDER):
    """Like :func:`calculate_carbon`, but returns a fully-attributed result.

    Prefer this (or :func:`engine.standardized_carbon_engine.calculate_standardized_emissions`)
    for anything that flows into governance, forecasting, or compliance
    reporting, since it exposes the grid-factor source and quality tier
    instead of just a number.
    """
    from engine.standardized_carbon_engine import calculate_standardized_emissions

    return calculate_standardized_emissions(
        provider=provider,
        region_code=region,
        vcpu_count=1,
        hours=vm,
        storage_gb=storage,
        network_gb=network,
        include_embodied=False,
    )


def get_carbon_region_key(region):
    """Return the resolved lookup key used for carbon intensity."""
    return resolve_region_key(region)
