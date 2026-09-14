"""Workload-level standardized carbon calculation.

Composes :mod:`engine.emission_factors` (the CCF-methodology physical
constants) into a single entry point that turns real AWS/GCP/Azure usage
line items into an auditable emissions estimate, instead of the flat
``vm_hours * 0.5`` heuristic the legacy :mod:`engine.carbon_engine` module
used. This is the function new ingestion code (connector sync, CUR/billing
export parsing) should call.

Every result carries the assumptions it relied on (utilization used,
whether the instance type was actually recognized, which grid-factor
quality tier applied) so the compliance layer can report data quality
honestly instead of presenting estimates as measured values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.emission_factors import (
    apply_pue,
    estimate_compute_energy_kwh,
    estimate_embodied_carbon_kg,
    estimate_memory_energy_kwh,
    estimate_network_energy_kwh,
    estimate_storage_energy_kwh,
    get_regional_intensity,
    normalize_provider,
    resolve_vcpu_count,
)


@dataclass
class StandardizedEmissionResult:
    """A fully-attributed emissions estimate for one workload/line item."""

    provider: str
    region_code: str
    vcpu_count: float
    hours: float
    avg_cpu_utilization: float

    energy_kwh: float
    compute_energy_kwh: float
    storage_energy_kwh: float
    network_energy_kwh: float
    memory_energy_kwh: float

    grid_co2e_per_kwh: float
    grid_quality_tier: str
    grid_source: str

    operational_carbon_kg: float
    embodied_carbon_kg: float
    total_carbon_kg: float

    instance_type_matched: bool
    data_quality: str = field(init=False)

    def __post_init__(self) -> None:
        if self.instance_type_matched and self.grid_quality_tier == "provider_sourced":
            self.data_quality = "high"
        elif self.grid_quality_tier in {"provider_sourced", "estimated_country_average"}:
            self.data_quality = "medium"
        else:
            self.data_quality = "low"


def calculate_standardized_emissions(
    *,
    provider: str,
    region_code: str,
    vcpu_count: float | None = None,
    instance_type: str | None = None,
    hours: float = 1.0,
    avg_cpu_utilization: float | None = None,
    storage_gb: float = 0.0,
    storage_type: str = "ssd",
    network_gb: float = 0.0,
    memory_gb: float = 0.0,
    include_embodied: bool = True,
) -> StandardizedEmissionResult:
    """Calculate operational + embodied carbon for one workload using real,
    provider/region-specific factors (Cloud Carbon Footprint methodology).

    Either ``vcpu_count`` or ``instance_type`` should be supplied for
    compute workloads; if both are omitted the result is still returned but
    ``instance_type_matched`` will be False and ``data_quality`` downgraded.
    """
    provider_norm = normalize_provider(provider)

    instance_matched = True
    if vcpu_count is None:
        if instance_type:
            vcpu_count, instance_matched = resolve_vcpu_count(instance_type)
        else:
            vcpu_count = 0.0
            instance_matched = False

    compute_kwh = estimate_compute_energy_kwh(provider_norm, vcpu_count, hours, avg_cpu_utilization)
    storage_kwh = estimate_storage_energy_kwh(storage_gb, hours, storage_type)
    network_kwh = estimate_network_energy_kwh(network_gb)
    memory_kwh = estimate_memory_energy_kwh(memory_gb, hours) if memory_gb else 0.0

    it_energy_kwh = compute_kwh + storage_kwh + network_kwh + memory_kwh
    facility_energy_kwh = apply_pue(it_energy_kwh, provider_norm)

    intensity = get_regional_intensity(provider_norm, region_code)
    operational_carbon_kg = facility_energy_kwh * intensity.co2e_per_kwh

    embodied_carbon_kg = (
        estimate_embodied_carbon_kg(vcpu_count, hours) if include_embodied and vcpu_count else 0.0
    )

    return StandardizedEmissionResult(
        provider=provider_norm,
        region_code=str(region_code or ""),
        vcpu_count=float(vcpu_count or 0.0),
        hours=float(hours),
        avg_cpu_utilization=avg_cpu_utilization if avg_cpu_utilization is not None else 0.5,
        energy_kwh=facility_energy_kwh,
        compute_energy_kwh=compute_kwh,
        storage_energy_kwh=storage_kwh,
        network_energy_kwh=network_kwh,
        memory_energy_kwh=memory_kwh,
        grid_co2e_per_kwh=intensity.co2e_per_kwh,
        grid_quality_tier=intensity.quality_tier,
        grid_source=intensity.source,
        operational_carbon_kg=operational_carbon_kg,
        embodied_carbon_kg=embodied_carbon_kg,
        total_carbon_kg=operational_carbon_kg + embodied_carbon_kg,
        instance_type_matched=instance_matched,
    )
