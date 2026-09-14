"""Recommendation engine for carbon optimization suggestions.

The manual calculator's ``get_recommendations(vm, storage, region, carbon)``
signature is kept for backward compatibility (``views/carbon_calculator.py``
calls it directly), but the region-migration suggestion is now backed by a
real number instead of a single hard-coded "if region == india, suggest
Europe" rule -- it looks up the actual sourced grid intensity for every
coarse region bucket and only recommends a move when it would truly help,
quantifying the estimated reduction.

For workloads that know their real cloud provider, region code, and vCPU
count (i.e. anything flowing through the standardized ingestion path),
prefer :mod:`ml.optimization_recommender`, which compares real
provider-region alternatives rather than the three coarse buckets
(``india`` / ``us`` / ``europe``) this simple calculator works with.
"""

from __future__ import annotations

from config import REGIONS, get_region_intensity, resolve_region_key


def get_recommendations(vm, storage, region, carbon):
    """Generate carbon optimization recommendations.

    Args:
        vm: Virtual machine hours
        storage: Storage in GB
        region: Region string (coarse bucket, e.g. "india", "us", "europe")
        carbon: Total carbon emissions in kg CO2

    Returns:
        List of recommendation strings
    """
    recommendations = []

    if vm < 50:
        recommendations.append("💡 Use serverless compute for lower resource needs")

    if storage > 500:
        recommendations.append("💾 Move cold data to archival storage for cost savings")

    current_key = resolve_region_key(region)
    current_intensity = get_region_intensity(region)
    cleanest_key = min(REGIONS, key=lambda candidate: get_region_intensity(candidate))
    cleanest_intensity = get_region_intensity(cleanest_key)
    if cleanest_key != current_key and cleanest_intensity < current_intensity * 0.85:
        reduction_pct = (1 - cleanest_intensity / current_intensity) * 100 if current_intensity else 0.0
        recommendations.append(
            f"🌍 Deploying in {cleanest_key.title()} instead of {current_key.title()} could cut this "
            f"workload's grid carbon intensity by roughly {reduction_pct:.0f}% "
            f"({current_intensity:.3f} -> {cleanest_intensity:.3f} kg CO2e/kWh)."
        )

    if carbon > 100:
        recommendations.append("⚙️ Optimize VM allocation and resource utilization")

    return recommendations
