"""Tests for ml.optimization_recommender."""

from __future__ import annotations

from ml.optimization_recommender import recommend_region_migrations, recommend_rightsizing


def test_region_migration_suggests_cleaner_regions_only():
    recs = recommend_region_migrations(
        provider="AWS", current_region="ap-south-1", vcpu_count=4, hours=730, storage_gb=100, network_gb=20
    )
    assert len(recs) > 0
    for rec in recs:
        assert rec.candidate_carbon_kg < rec.current_carbon_kg
        assert rec.carbon_reduction_pct > 0
    # Results should be sorted best-first.
    assert recs == sorted(recs, key=lambda r: r.carbon_reduction_pct, reverse=True)


def test_region_migration_from_already_cleanest_region_returns_few_or_no_gains():
    recs = recommend_region_migrations(
        provider="AWS", current_region="eu-north-1", vcpu_count=4, hours=730
    )
    # Sweden is already one of the cleanest AWS regions in our candidate list --
    # there should be no (or very few) candidates that beat it.
    assert len(recs) <= 1


def test_rightsizing_flags_low_utilization_workloads():
    rec = recommend_rightsizing(avg_cpu_utilization=0.05, vcpu_count=8)
    assert rec is not None
    assert rec.suggested_vcpu < rec.current_vcpu
    assert rec.estimated_carbon_reduction_pct > 0


def test_rightsizing_does_not_flag_well_utilized_workloads():
    assert recommend_rightsizing(avg_cpu_utilization=0.75, vcpu_count=8) is None


def test_rightsizing_ignores_single_vcpu_workloads():
    assert recommend_rightsizing(avg_cpu_utilization=0.05, vcpu_count=1) is None
