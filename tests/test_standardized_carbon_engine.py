"""Tests for engine.standardized_carbon_engine."""

from __future__ import annotations

from engine.standardized_carbon_engine import calculate_standardized_emissions


def test_same_workload_costs_more_carbon_in_dirtier_region():
    clean = calculate_standardized_emissions(provider="AWS", region_code="eu-north-1", instance_type="m5.xlarge", hours=730)
    dirty = calculate_standardized_emissions(provider="AWS", region_code="ap-south-1", instance_type="m5.xlarge", hours=730)
    assert clean.operational_carbon_kg < dirty.operational_carbon_kg
    # Energy consumption itself should be identical -- only the grid differs.
    assert clean.energy_kwh == dirty.energy_kwh


def test_data_quality_high_when_instance_and_region_both_resolved():
    result = calculate_standardized_emissions(provider="AWS", region_code="us-east-1", instance_type="m5.large", hours=1)
    assert result.instance_type_matched is True
    assert result.grid_quality_tier == "provider_sourced"
    assert result.data_quality == "high"


def test_data_quality_downgrades_for_unknown_instance():
    result = calculate_standardized_emissions(provider="AWS", region_code="us-east-1", instance_type="totally-unknown", hours=1)
    assert result.instance_type_matched is False
    assert result.data_quality == "medium"


def test_embodied_carbon_included_only_when_requested():
    with_embodied = calculate_standardized_emissions(
        provider="AWS", region_code="us-east-1", vcpu_count=4, hours=730, include_embodied=True
    )
    without_embodied = calculate_standardized_emissions(
        provider="AWS", region_code="us-east-1", vcpu_count=4, hours=730, include_embodied=False
    )
    assert with_embodied.embodied_carbon_kg > 0
    assert without_embodied.embodied_carbon_kg == 0
    assert with_embodied.total_carbon_kg > without_embodied.total_carbon_kg


def test_no_vcpu_or_instance_type_still_returns_a_result_with_low_confidence():
    result = calculate_standardized_emissions(provider="AWS", region_code="us-east-1", hours=1)
    assert result.instance_type_matched is False
    assert result.vcpu_count == 0.0
