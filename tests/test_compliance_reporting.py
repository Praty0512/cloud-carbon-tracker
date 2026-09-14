"""Tests for compliance.reporting: standards-grounded control checklist."""

from __future__ import annotations

from compliance.reporting import data_quality_summary, standards_control_checklist


def test_data_quality_summary_handles_empty_breakdown():
    summary = data_quality_summary({"high": 0, "medium": 0, "low": 0, "unknown": 0})
    assert summary["total_records"] == 0


def test_data_quality_summary_computes_percentages():
    summary = data_quality_summary({"high": 8, "medium": 1, "low": 1, "unknown": 0})
    assert summary["total_records"] == 10
    assert summary["high_pct"] == 80.0


def test_checklist_flags_missing_market_instrument():
    headline = {"total_carbon": 100.0, "connectors": 1, "reports": 2, "team_members": 3}
    dq = data_quality_summary({"high": 5, "medium": 0, "low": 0, "unknown": 0})
    controls = standards_control_checklist(headline=headline, data_quality=dq, market_instrument_count=0)
    scope2 = next(c for c in controls if "Scope 2" in c.control)
    assert scope2.status == "Partial"
    assert "GHG Protocol" in scope2.standard_reference

    dq_control = next(c for c in controls if "data quality" in c.control.lower())
    assert dq_control.status == "Healthy"
    assert "ISO 14064-1" in dq_control.standard_reference


def test_checklist_upgrades_scope2_when_market_instrument_present():
    headline = {"total_carbon": 100.0, "connectors": 1, "reports": 1, "team_members": 1}
    dq = data_quality_summary({"high": 1, "medium": 0, "low": 0, "unknown": 0})
    controls = standards_control_checklist(headline=headline, data_quality=dq, market_instrument_count=2)
    scope2 = next(c for c in controls if "Scope 2" in c.control)
    assert scope2.status == "Healthy"


def test_checklist_reports_missing_when_no_telemetry_at_all():
    headline = {"total_carbon": 0.0, "connectors": 0, "reports": 0, "team_members": 0}
    dq = data_quality_summary({"high": 0, "medium": 0, "low": 0, "unknown": 0})
    controls = standards_control_checklist(headline=headline, data_quality=dq, market_instrument_count=0)
    scope2 = next(c for c in controls if "Scope 2" in c.control)
    assert scope2.status == "Missing"
