"""Standardized, provider-real emission factor engine.

This module implements the calculation methodology published by the
`Cloud Carbon Footprint <https://www.cloudcarbonfootprint.org/docs/methodology/>`_
(CCF) open-source project -- the same approach independently referenced by
AWS, Microsoft, and Google when they describe how third parties estimate
cloud carbon -- rather than the flat, made-up coefficients the app used to
ship with (a single ``COMPUTE_FACTOR = 0.5`` applied to every workload,
country-bucket "intensity" values on an arbitrary 0-1 scale).

Everything sourced from a citeable dataset is tagged with a
``quality_tier`` of ``"provider_sourced"``; everything that had to be
filled in with a documented country-average estimate (because no
provider-specific figure was published for that region) is tagged
``"estimated_country_average"``. That tiering is not decorative -- GHG
Protocol / ISO 14064-1 both expect an inventory to disclose the quality of
its activity data, and :mod:`compliance.reporting` surfaces this field
directly in the workspace's data-quality disclosure.

Sources
-------
- Compute wattage curves & PUE: Cloud Carbon Footprint methodology docs
  (derived from the Etsy "Cloud Jewels" model and Teads engineering
  research). https://www.cloudcarbonfootprint.org/docs/methodology/
- Embodied carbon: Green Software Foundation Software Carbon Intensity
  (SCI) specification, ``M = TE * (TR / EL) * (RR / TR)``.
  https://www.cloudcarbonfootprint.org/docs/embodied-emissions/
- Regional grid carbon intensity: EPA eGRID (US), European Environment
  Agency (EU), Google (GCP regions), EMA Singapore, carbonfootprint.com
  international factors, as compiled by the Cloud Carbon Footprint project:
  https://github.com/cloud-carbon-footprint/cloud-carbon-coefficients
- A handful of regions (Poland, Norway, Spain, UAE, Saudi Arabia, Israel,
  Turkey) are not in that dataset; those use documented IEA/Ember national
  average estimates and are flagged accordingly below.

This module is deliberately independent from ``config.py``'s coarse
country-bucket table (``india`` / ``us`` / ``europe``), which remains as a
lightweight fallback for the manual calculator UI. New code that knows the
actual cloud provider and region code should use this module instead.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

DATA_DIR = Path(__file__).parent.parent / "data"

QualityTier = Literal["provider_sourced", "estimated_country_average", "coarse_fallback"]

# ---------------------------------------------------------------------------
# Power Usage Effectiveness (PUE) -- published, provider-specific.
# Source: Cloud Carbon Footprint methodology (citing provider sustainability
# disclosures). Applied as a multiplier on IT energy to account for data
# center cooling/power-delivery overhead.
# ---------------------------------------------------------------------------
PUE_BY_PROVIDER: dict[str, float] = {
    "AWS": 1.135,
    "GCP": 1.1,
    "AZURE": 1.185,
}
DEFAULT_PUE = 1.2  # conservative average used when the provider is unknown

# ---------------------------------------------------------------------------
# Per-vCPU power draw curve (Watts at 0% and 100% utilization), averaged
# across microarchitectures. Source: Cloud Carbon Footprint methodology.
# ---------------------------------------------------------------------------
CPU_POWER_CURVE_WATTS: dict[str, tuple[float, float]] = {
    "AWS": (0.74, 3.5),
    "GCP": (0.71, 4.26),
    "AZURE": (0.78, 3.76),
}
DEFAULT_CPU_POWER_CURVE_WATTS = (0.75, 3.84)

# Default average CPU utilization assumed when a workload's actual
# utilization telemetry is not available. Source: hyperscale datacenter
# average from the 2016 U.S. Data Center Energy Usage Report, the same
# default CCF uses.
DEFAULT_CPU_UTILIZATION = 0.50

# Networking energy intensity (inter-datacenter egress only).
NETWORK_KWH_PER_GB = 0.001

# Memory energy intensity (average of Crucial/Micron DIMM specs).
MEMORY_KW_PER_GB = 0.000392

# Storage energy intensity, Watt-hours per Terabyte-hour of *allocated*
# (not just used) capacity -- CCF applies this to allocated bytes because
# that is what the physical infrastructure must provision for.
STORAGE_WH_PER_TB_HOUR = {
    "hdd": 0.65,
    "ssd": 1.2,
}

# ---------------------------------------------------------------------------
# Embodied carbon (Software Carbon Intensity spec: M = TE * (TR/EL) * (RR/TR))
# TE (total embodied emissions per physical server) and typical server vCPU
# capacity are coarse, documented industry defaults -- CCF derives per
# instance-family TE from the Boavizta API; without that database this app
# uses a single conservative reference point (representative of a modern
# 2-socket rack server, similar order of magnitude to the Dell PowerEdge
# R740 lifecycle assessment CCF itself cites) and is transparent that this
# is an approximation.
# ---------------------------------------------------------------------------
EMBODIED_CARBON_PER_SERVER_KG = 1500.0
SERVER_EXPECTED_LIFESPAN_YEARS = 4.0
SERVER_REFERENCE_VCPU_CAPACITY = 64

# ---------------------------------------------------------------------------
# A compact vCPU/memory lookup for common instance families, used to turn a
# billing export's "instance type" column into a real vCPU count instead of
# assuming every line item is a single generic unit. Unmatched instance
# types fall back to DEFAULT_VCPU_ASSUMPTION with a lower confidence flag.
# ---------------------------------------------------------------------------
DEFAULT_VCPU_ASSUMPTION = 2

INSTANCE_VCPU_TABLE: dict[str, int] = {
    # AWS (EC2)
    "t3.nano": 2, "t3.micro": 2, "t3.small": 2, "t3.medium": 2,
    "t3.large": 2, "t3.xlarge": 4, "t3.2xlarge": 8,
    "t3a.micro": 2, "t3a.small": 2, "t3a.medium": 2, "t3a.large": 2,
    "m5.large": 2, "m5.xlarge": 4, "m5.2xlarge": 8, "m5.4xlarge": 16, "m5.8xlarge": 32,
    "m6i.large": 2, "m6i.xlarge": 4, "m6i.2xlarge": 8, "m6i.4xlarge": 16,
    "c5.large": 2, "c5.xlarge": 4, "c5.2xlarge": 8, "c5.4xlarge": 16,
    "c6i.large": 2, "c6i.xlarge": 4, "c6i.2xlarge": 8,
    "r5.large": 2, "r5.xlarge": 4, "r5.2xlarge": 8, "r5.4xlarge": 16,
    # GCP (Compute Engine)
    "e2-micro": 2, "e2-small": 2, "e2-medium": 2,
    "e2-standard-2": 2, "e2-standard-4": 4, "e2-standard-8": 8, "e2-standard-16": 16,
    "n2-standard-2": 2, "n2-standard-4": 4, "n2-standard-8": 8, "n2-standard-16": 16,
    "n1-standard-1": 1, "n1-standard-2": 2, "n1-standard-4": 4, "n1-standard-8": 8,
    "c2-standard-4": 4, "c2-standard-8": 8, "c2-standard-16": 16,
    # Azure (Virtual Machines)
    "standard_b2s": 2, "standard_b2ms": 2, "standard_b4ms": 4,
    "standard_d2s_v5": 2, "standard_d4s_v5": 4, "standard_d8s_v5": 8, "standard_d16s_v5": 16,
    "standard_f2s_v2": 2, "standard_f4s_v2": 4, "standard_f8s_v2": 8,
    "standard_e2s_v5": 2, "standard_e4s_v5": 4, "standard_e8s_v5": 8,
}


def resolve_vcpu_count(instance_type: object) -> tuple[int, bool]:
    """Return (vcpu_count, matched) for a billing-export instance type string.

    ``matched`` is False when the instance type could not be resolved and the
    documented default assumption was used -- callers should propagate this
    into a data-quality flag rather than silently presenting an assumption
    as measured fact.
    """
    key = str(instance_type or "").strip().lower()
    if key in INSTANCE_VCPU_TABLE:
        return INSTANCE_VCPU_TABLE[key], True
    # Try stripping cloud-specific size suffixes / prefixes (e.g. "db.m5.large")
    for known_key, vcpus in INSTANCE_VCPU_TABLE.items():
        if key.endswith(known_key):
            return vcpus, True
    return DEFAULT_VCPU_ASSUMPTION, False


@lru_cache(maxsize=None)
def _load_provider_grid_table(provider: str) -> dict:
    """Load and cache the sourced grid-emissions JSON file for a provider."""
    filename = {
        "AWS": "grid_emissions_aws.json",
        "GCP": "grid_emissions_gcp.json",
        "AZURE": "grid_emissions_azure.json",
    }.get(provider.upper())
    if not filename:
        return {}
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as file_handle:
        payload = json.load(file_handle)
    return payload.get("regions", {})


@dataclass(frozen=True)
class RegionalIntensity:
    """A resolved grid carbon intensity figure with provenance."""

    provider: str
    region_code: str
    co2e_per_kwh: float
    quality_tier: QualityTier
    source: str
    location: str | None = None


def get_regional_intensity(provider: str, region_code: object) -> RegionalIntensity:
    """Return the sourced grid carbon intensity for a real provider region code.

    Falls back to the coarse, config.py country-bucket estimate (tagged
    ``coarse_fallback``) only when the specific region code is not in our
    sourced dataset -- this keeps every calculation defensible and labeled
    rather than silently guessing.
    """
    provider_key = str(provider or "").upper()
    region_key = str(region_code or "").strip()
    table = _load_provider_grid_table(provider_key)

    if region_key in table:
        entry = table[region_key]
        return RegionalIntensity(
            provider=provider_key,
            region_code=region_key,
            co2e_per_kwh=float(entry["co2e_per_kwh"]),
            quality_tier="provider_sourced" if "estimate" not in entry.get("source", "").lower() else "estimated_country_average",
            source=entry.get("source", "unknown"),
            location=entry.get("location"),
        )

    # Fall back to the coarse country-bucket table shared with the manual
    # calculator (config.REGION_INTENSITY), so callers always get a number.
    from config import get_region_intensity, resolve_region_key  # local import avoids a cycle

    coarse_key = resolve_region_key(region_key)
    return RegionalIntensity(
        provider=provider_key,
        region_code=region_key,
        co2e_per_kwh=get_region_intensity(region_key),
        quality_tier="coarse_fallback",
        source=f"config.REGION_INTENSITY[{coarse_key}] (no provider-specific figure available)",
        location=None,
    )


def estimate_compute_energy_kwh(
    provider: str,
    vcpu_count: float,
    hours: float,
    avg_cpu_utilization: float | None = None,
) -> float:
    """CCF compute formula: Watts = min + (utilization * (max - min)); Wh = Watts * vCPU-hours."""
    min_w, max_w = CPU_POWER_CURVE_WATTS.get(str(provider or "").upper(), DEFAULT_CPU_POWER_CURVE_WATTS)
    utilization = DEFAULT_CPU_UTILIZATION if avg_cpu_utilization is None else max(0.0, min(1.0, avg_cpu_utilization))
    avg_watts_per_vcpu = min_w + utilization * (max_w - min_w)
    watt_hours = avg_watts_per_vcpu * max(vcpu_count, 0.0) * max(hours, 0.0)
    return watt_hours / 1000.0


def estimate_storage_energy_kwh(storage_gb: float, hours: float, storage_type: str = "ssd") -> float:
    """CCF storage formula applied to allocated capacity over the billing window."""
    wh_per_tb_hour = STORAGE_WH_PER_TB_HOUR.get(str(storage_type or "ssd").lower(), STORAGE_WH_PER_TB_HOUR["ssd"])
    tb = max(storage_gb, 0.0) / 1000.0
    watt_hours = tb * wh_per_tb_hour * max(hours, 0.0)
    return watt_hours / 1000.0


def estimate_network_energy_kwh(network_gb: float) -> float:
    """CCF networking formula: 0.001 kWh per GB of inter-datacenter transfer."""
    return max(network_gb, 0.0) * NETWORK_KWH_PER_GB


def estimate_memory_energy_kwh(memory_gb: float, hours: float) -> float:
    """CCF memory formula for memory provisioned beyond the SPECpower baseline."""
    return max(memory_gb, 0.0) * MEMORY_KW_PER_GB * max(hours, 0.0)


def apply_pue(energy_kwh: float, provider: str) -> float:
    """Scale IT-equipment energy up to facility energy using provider PUE."""
    pue = PUE_BY_PROVIDER.get(str(provider or "").upper(), DEFAULT_PUE)
    return energy_kwh * pue


def estimate_embodied_carbon_kg(vcpu_reserved: float, hours: float, vcpu_capacity: int = SERVER_REFERENCE_VCPU_CAPACITY) -> float:
    """Software Carbon Intensity embodied-carbon formula: M = TE * (TR/EL) * (RR/TR)."""
    if vcpu_capacity <= 0:
        vcpu_capacity = SERVER_REFERENCE_VCPU_CAPACITY
    lifespan_hours = SERVER_EXPECTED_LIFESPAN_YEARS * 365 * 24
    time_share = max(hours, 0.0) / lifespan_hours
    resource_share = max(vcpu_reserved, 0.0) / vcpu_capacity
    return EMBODIED_CARBON_PER_SERVER_KG * time_share * resource_share


def normalize_provider(provider: object) -> str:
    """Normalize a free-text provider label to AWS / GCP / AZURE / UNKNOWN."""
    text = re.sub(r"[^a-z]", "", str(provider or "").lower())
    if text in {"aws", "amazon", "amazonwebservices"}:
        return "AWS"
    if text in {"gcp", "google", "googlecloud"}:
        return "GCP"
    if text in {"azure", "microsoft", "microsoftazure"}:
        return "AZURE"
    return "UNKNOWN"
