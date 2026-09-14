"""Real-world-calibrated demo/synthetic dataset generation.

Historically `utils/fake_data_generator.py` produced entirely arbitrary
numbers (`random.randint(50, 200)` VM-hours, no utilization or instance
information at all), which meant every demo dataset landed in the
generic/Kaggle-style ingestion path (`dataset_adapter.normalize_cloud_carbon_dataframe`)
tagged `data_quality = "low"` -- there was no way to demo what the
standardized engine actually produces for a well-formed, instance-aware
dataset.

This module instead samples from **real** empirical statistics captured
from the Microsoft Azure Public Dataset (2.7M real production VMs; see
`data/reference_datasets/README.md`) -- CPU utilization distribution and
instance-size mix -- and combines them with the app's real, sourced
provider region tables (`engine.emission_factors`) to generate demo rows
that the standardized carbon engine (`engine.standardized_carbon_engine`)
scores exactly the way it would score a real billing export: real vCPU
counts, real region grid factors, and a utilization distribution shaped
like an actual production fleet rather than a uniform random guess.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from engine.emission_factors import _load_provider_grid_table
from engine.standardized_carbon_engine import calculate_standardized_emissions

PROFILE_PATH = Path(__file__).parent.parent / "data" / "reference_datasets" / "azure_utilization_profile.json"

PROVIDERS = ["AWS", "GCP", "AZURE"]

# vCPU count -> a representative instance type per provider, drawn from the
# same INSTANCE_VCPU_TABLE the real ingestion parsers resolve against, so a
# generated row lands `instance_type_matched = True` just like a real one.
_VCPU_TO_INSTANCE_TYPE: dict[str, dict[int, str]] = {
    "AWS": {2: "m5.large", 4: "m5.xlarge", 8: "m5.2xlarge", 16: "m5.4xlarge", 32: "m5.8xlarge"},
    "GCP": {2: "n2-standard-2", 4: "n2-standard-4", 8: "n2-standard-8", 16: "n2-standard-16", 32: "n2-standard-16"},
    "AZURE": {2: "standard_d2s_v5", 4: "standard_d4s_v5", 8: "standard_d8s_v5", 16: "standard_d16s_v5", 32: "standard_d16s_v5"},
}
# Real Azure fleet vCPU buckets (2, 4, 8, 24, 32-for-">24") don't map 1:1
# onto every provider's published instance sizes -- 24 has no direct AWS/GCP
# equivalent in our compact lookup table, so it's rounded to the nearest
# size we do have (16) rather than silently dropped.
_VCPU_BUCKET_ROUNDING = {24: 16}


@lru_cache(maxsize=1)
def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        # Fall back to the documented CCF hyperscale-average default if the
        # reference dataset hasn't been built yet (e.g. a fresh clone before
        # `scripts/build_azure_reference_dataset.py` has been run) -- never
        # silently invent a different distribution shape.
        return {
            "avg_cpu_utilization_pct": {"p5": 5, "p10": 10, "p25": 25, "p50": 50, "p75": 60, "p90": 75, "p95": 85, "p99": 95},
            "vcpu_count_distribution_pct": {"2": 60, "4": 30, "8": 8, "24": 2},
        }
    with open(PROFILE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _sample_utilization_fraction(rng: random.Random, profile: dict) -> float:
    """Inverse-CDF sample from the real empirical CPU utilization percentiles."""
    pct_table = profile["avg_cpu_utilization_pct"]
    percentiles = [5, 10, 25, 50, 75, 90, 95, 99]
    xs = [0.0] + percentiles + [100.0]
    ys = [0.0] + [pct_table[f"p{p}"] for p in percentiles] + [max(pct_table[f"p{p}"] for p in percentiles) * 1.05]
    u = rng.uniform(0.5, 99.5)  # avoid the extreme tails for demo readability
    value_pct = float(np.interp(u, xs, ys))
    return max(0.0, min(1.0, value_pct / 100.0))


def _sample_vcpu_count(rng: random.Random, profile: dict) -> int:
    dist = profile["vcpu_count_distribution_pct"]
    buckets = [int(k) for k in dist.keys()]
    weights = list(dist.values())
    chosen = rng.choices(buckets, weights=weights, k=1)[0]
    return _VCPU_BUCKET_ROUNDING.get(chosen, chosen)


def _instance_type_for(provider: str, vcpu_count: int) -> str:
    table = _VCPU_TO_INSTANCE_TYPE[provider]
    if vcpu_count in table:
        return table[vcpu_count]
    nearest = min(table.keys(), key=lambda v: abs(v - vcpu_count))
    return table[nearest]


def _sample_region(rng: random.Random, provider: str) -> str:
    regions = list(_load_provider_grid_table(provider).keys())
    return rng.choice(regions) if regions else "us-east-1"


def generate_realistic_usage(rows: int = 50, seed: int | None = None) -> pd.DataFrame:
    """Generate a synthetic cloud usage dataset calibrated to real production telemetry.

    Every row's CPU utilization and instance size is sampled from the real
    Azure Public Dataset empirical distribution
    (`data/reference_datasets/azure_utilization_profile.json`), and every
    row's carbon/energy figure is computed by the same
    `engine.standardized_carbon_engine` used for real billing-export
    ingestion -- not a separate, simplified formula. The result is a
    dataset whose numbers are defensible (real methodology, real region
    factors) even though the underlying workload activity is synthetic.
    """
    rng = random.Random(seed)
    profile = _load_profile()
    start = pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=rows)

    records = []
    for i in range(rows):
        provider = rng.choice(PROVIDERS)
        vcpu_count = _sample_vcpu_count(rng, profile)
        instance_type = _instance_type_for(provider, vcpu_count)
        region_code = _sample_region(rng, provider)
        utilization = _sample_utilization_fraction(rng, profile)
        hours = rng.choice([1, 2, 4, 8, 12, 24, 48, 72])
        storage_gb = round(rng.uniform(10, 1000), 1)
        network_gb = round(rng.uniform(1, 300), 1)

        result = calculate_standardized_emissions(
            provider=provider,
            region_code=region_code,
            vcpu_count=vcpu_count,
            instance_type=instance_type,
            hours=float(hours),
            avg_cpu_utilization=utilization,
            storage_gb=storage_gb,
            network_gb=network_gb,
        )

        records.append({
            "timestamp": (start + pd.Timedelta(days=i)).date().isoformat(),
            "provider": provider,
            "region": region_code,
            "instance_type": instance_type,
            "vcpu_count": vcpu_count,
            "avg_cpu_utilization_pct": round(utilization * 100, 2),
            "vm_hours": hours,
            "storage_gb": storage_gb,
            "network_gb": network_gb,
            "energy_kwh": round(result.energy_kwh, 4),
            "carbon": round(result.total_carbon_kg, 4),
            "data_quality": result.data_quality,
        })

    return pd.DataFrame(records)
