"""Tests for engine.emission_factors: the sourced physical constants and lookups."""

from __future__ import annotations

import pytest

from engine import emission_factors as ef


def test_regional_intensity_uses_sourced_table_for_known_region():
    result = ef.get_regional_intensity("AWS", "eu-north-1")
    assert result.quality_tier == "provider_sourced"
    assert result.co2e_per_kwh == 0.008  # Sweden, near-zero-carbon grid (kg CO2e/kWh)
    assert "EEA" in result.source


def test_regional_intensity_orders_regions_correctly():
    """Sweden's grid must be far cleaner than India's -- a sanity check on the sourced data itself."""
    sweden = ef.get_regional_intensity("AWS", "eu-north-1")
    india = ef.get_regional_intensity("AWS", "ap-south-1")
    assert sweden.co2e_per_kwh < india.co2e_per_kwh


def test_regional_intensity_falls_back_to_coarse_bucket_for_unknown_region():
    result = ef.get_regional_intensity("AWS", "totally-made-up-region-42")
    assert result.quality_tier == "coarse_fallback"
    assert result.co2e_per_kwh > 0


def test_resolve_vcpu_count_known_instance():
    vcpus, matched = ef.resolve_vcpu_count("m5.2xlarge")
    assert matched is True
    assert vcpus == 8


def test_resolve_vcpu_count_unknown_instance_uses_documented_default():
    vcpus, matched = ef.resolve_vcpu_count("some.unknown.type")
    assert matched is False
    assert vcpus == ef.DEFAULT_VCPU_ASSUMPTION


def test_compute_energy_scales_with_utilization():
    low_util = ef.estimate_compute_energy_kwh("AWS", vcpu_count=1, hours=1, avg_cpu_utilization=0.0)
    high_util = ef.estimate_compute_energy_kwh("AWS", vcpu_count=1, hours=1, avg_cpu_utilization=1.0)
    min_w, max_w = ef.CPU_POWER_CURVE_WATTS["AWS"]
    assert low_util == min_w / 1000.0
    assert high_util == max_w / 1000.0
    assert high_util > low_util


def test_pue_multiplies_energy_by_provider_specific_factor():
    energy = 10.0
    assert ef.apply_pue(energy, "GCP") == energy * ef.PUE_BY_PROVIDER["GCP"]
    assert ef.apply_pue(energy, "unknown-provider") == energy * ef.DEFAULT_PUE


def test_embodied_carbon_scales_with_reserved_share_and_time():
    full_server_month = ef.estimate_embodied_carbon_kg(
        vcpu_reserved=ef.SERVER_REFERENCE_VCPU_CAPACITY, hours=730
    )
    half_server_month = ef.estimate_embodied_carbon_kg(
        vcpu_reserved=ef.SERVER_REFERENCE_VCPU_CAPACITY / 2, hours=730
    )
    assert half_server_month == pytest.approx(full_server_month / 2)


def test_sourced_grid_factors_are_plausible_kg_co2e_per_kwh_not_metric_tons():
    """Regression test for a real bug found while validating against real data:
    the cloud-carbon-coefficients source CSVs publish metric tons CO2e/kWh,
    and an earlier pass copied those numbers in as if they were already
    kg CO2e/kWh -- silently under-reporting every provider-sourced region's
    carbon intensity by 1000x. A real electricity grid is on the order of
    0.01-1.0 kg CO2e/kWh (a near-zero-carbon grid like Sweden's is ~0.01,
    a coal-heavy grid like India's or Poland's can exceed 0.7); this bounds
    every provider-sourced (non-estimated) region to that plausible range so
    a future unit regression fails loudly instead of silently shipping.
    """
    for provider, region in [("AWS", "us-east-1"), ("GCP", "us-central1"), ("AZURE", "East US")]:
        result = ef.get_regional_intensity(provider, region)
        assert result.quality_tier == "provider_sourced"
        assert 0.01 <= result.co2e_per_kwh <= 1.0, (
            f"{provider}/{region} co2e_per_kwh={result.co2e_per_kwh} is implausible "
            "for a real electricity grid -- check for a metric-tons-vs-kg unit bug"
        )


def test_normalize_provider_variants():
    assert ef.normalize_provider("amazon web services") == "AWS"
    assert ef.normalize_provider("Google Cloud") == "GCP"
    assert ef.normalize_provider("Microsoft Azure") == "AZURE"
    assert ef.normalize_provider("something-else") == "UNKNOWN"
