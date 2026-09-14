"""Tests for compliance.ghg_protocol: GHG Protocol Scope 2 dual reporting."""

from __future__ import annotations

from compliance.ghg_protocol import aggregate_scope2, scope2_dual_report


def test_without_market_instrument_falls_back_to_location_based_and_is_flagged():
    result = scope2_dual_report(energy_kwh=100, provider="AWS", region_code="ap-south-1")
    assert result.market_based_kg_co2e == result.location_based_kg_co2e
    assert result.dual_reporting_complete is False
    assert "fallback" in result.market_based_method


def test_with_market_instrument_produces_a_different_market_based_number():
    result = scope2_dual_report(
        energy_kwh=100,
        provider="AWS",
        region_code="ap-south-1",
        market_instrument={"type": "ppa", "co2e_per_kwh": 0.01, "source": "Test PPA"},
    )
    assert result.dual_reporting_complete is True
    assert result.market_based_kg_co2e == 1.0
    assert result.market_based_kg_co2e != result.location_based_kg_co2e
    assert "ppa" in result.market_based_method


def test_aggregate_scope2_computes_coverage_percentage():
    with_ppa = scope2_dual_report(
        energy_kwh=50, provider="AWS", region_code="us-east-1",
        market_instrument={"type": "ppa", "co2e_per_kwh": 0.0, "source": "test"},
    )
    without_ppa = scope2_dual_report(energy_kwh=50, provider="AWS", region_code="us-east-1")
    totals = aggregate_scope2([with_ppa, without_ppa])
    assert totals["workloads_total"] == 2
    assert totals["workloads_with_market_instrument"] == 1
    assert totals["market_instrument_coverage_pct"] == 50.0


def test_aggregate_scope2_empty_list_does_not_crash():
    totals = aggregate_scope2([])
    assert totals["workloads_total"] == 0
    assert totals["market_instrument_coverage_pct"] == 0.0
