"""Tests for engine.recommendation_engine (legacy calculator, quantified)."""

from __future__ import annotations

from engine.recommendation_engine import get_recommendations


def test_high_intensity_region_gets_a_quantified_migration_suggestion():
    recs = get_recommendations(vm=20, storage=100, region="india", carbon=50)
    migration_recs = [r for r in recs if "cut this workload" in r]
    assert len(migration_recs) == 1
    assert "%" in migration_recs[0]


def test_already_clean_region_gets_no_migration_suggestion():
    recs = get_recommendations(vm=20, storage=100, region="europe", carbon=10)
    migration_recs = [r for r in recs if "cut this workload" in r]
    assert migration_recs == []


def test_low_vm_hours_triggers_serverless_tip():
    recs = get_recommendations(vm=10, storage=100, region="us", carbon=5)
    assert any("serverless" in r for r in recs)


def test_high_storage_triggers_archival_tip():
    recs = get_recommendations(vm=100, storage=600, region="us", carbon=5)
    assert any("archival" in r for r in recs)
