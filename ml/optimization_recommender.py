"""Quantified optimization recommendations.

The original ``engine/recommendation_engine.py`` returned four hard-coded
sentences gated by simple thresholds (e.g. "if region == 'india': suggest
Europe") with no actual number behind them. This module produces
recommendations backed by the same standardized, real-provider-data engine
used for ingestion (:mod:`engine.standardized_carbon_engine`), so a
suggestion reads "moving this workload from ap-south-1 to eu-north-1 would
cut its operational carbon by roughly 91% (4.97kg -> 0.06kg per month)"
instead of a generic tip.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.standardized_carbon_engine import calculate_standardized_emissions

# A representative shortlist of regions per provider to compare against,
# rather than exhaustively scanning every region in the sourced tables --
# keeps recommendations fast and focused on realistic, commonly-used
# alternatives. Fed from the same sourced data files as ingestion.
CANDIDATE_REGIONS = {
    "AWS": ["us-east-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1", "ap-south-1", "ap-southeast-1", "sa-east-1", "ca-central-1"],
    "GCP": ["us-central1", "us-west1", "europe-west1", "europe-west6", "europe-north1", "asia-south1", "asia-southeast1", "southamerica-east1", "northamerica-northeast1"],
    "AZURE": ["East US", "West US 2", "North Europe", "West Europe", "Sweden Central", "France Central", "Central India", "Southeast Asia", "Brazil South", "Canada Central"],
}


@dataclass
class RegionMigrationRecommendation:
    provider: str
    current_region: str
    candidate_region: str
    current_carbon_kg: float
    candidate_carbon_kg: float
    carbon_reduction_pct: float
    carbon_saved_kg: float


@dataclass
class RightsizingRecommendation:
    reason: str
    current_vcpu: float
    suggested_vcpu: float
    estimated_carbon_reduction_pct: float


def recommend_region_migrations(
    *,
    provider: str,
    current_region: str,
    vcpu_count: float,
    hours: float,
    storage_gb: float = 0.0,
    network_gb: float = 0.0,
    top_n: int = 3,
) -> list[RegionMigrationRecommendation]:
    """Rank candidate regions for the same provider by estimated carbon reduction."""
    baseline = calculate_standardized_emissions(
        provider=provider,
        region_code=current_region,
        vcpu_count=vcpu_count,
        hours=hours,
        storage_gb=storage_gb,
        network_gb=network_gb,
        include_embodied=False,
    )

    candidates = CANDIDATE_REGIONS.get(baseline.provider, [])
    scored: list[RegionMigrationRecommendation] = []
    for region in candidates:
        if region == current_region:
            continue
        alt = calculate_standardized_emissions(
            provider=provider,
            region_code=region,
            vcpu_count=vcpu_count,
            hours=hours,
            storage_gb=storage_gb,
            network_gb=network_gb,
            include_embodied=False,
        )
        if alt.total_carbon_kg >= baseline.total_carbon_kg:
            continue
        reduction_pct = (
            (baseline.total_carbon_kg - alt.total_carbon_kg) / baseline.total_carbon_kg * 100
            if baseline.total_carbon_kg > 0
            else 0.0
        )
        scored.append(
            RegionMigrationRecommendation(
                provider=baseline.provider,
                current_region=current_region,
                candidate_region=region,
                current_carbon_kg=baseline.total_carbon_kg,
                candidate_carbon_kg=alt.total_carbon_kg,
                carbon_reduction_pct=reduction_pct,
                carbon_saved_kg=baseline.total_carbon_kg - alt.total_carbon_kg,
            )
        )

    scored.sort(key=lambda rec: rec.carbon_reduction_pct, reverse=True)
    return scored[:top_n]


def recommend_rightsizing(avg_cpu_utilization: float, vcpu_count: float) -> RightsizingRecommendation | None:
    """Flag workloads with low measured utilization as right-sizing candidates.

    Uses the same CCF compute curve to estimate the emissions impact:
    energy scales with vCPU count and average utilization, so halving
    provisioned vCPUs for a chronically under-utilized workload roughly
    halves compute energy even before accounting for the (typically
    unchanged) utilization on the smaller instance.
    """
    if avg_cpu_utilization is None or avg_cpu_utilization >= 0.20 or vcpu_count <= 1:
        return None

    suggested_vcpu = max(1.0, vcpu_count / 2)
    estimated_reduction_pct = (1 - suggested_vcpu / vcpu_count) * 100
    return RightsizingRecommendation(
        reason=(
            f"Measured average CPU utilization is {avg_cpu_utilization * 100:.0f}%, "
            "well below the 50% hyperscale baseline this workload is provisioned against."
        ),
        current_vcpu=vcpu_count,
        suggested_vcpu=suggested_vcpu,
        estimated_carbon_reduction_pct=estimated_reduction_pct,
    )
