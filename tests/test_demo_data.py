"""Tests for utils.demo_data: real-telemetry-calibrated demo data generation."""

from __future__ import annotations

from utils.demo_data import generate_realistic_usage
from utils.fake_data_generator import generate_fake_usage


def test_generate_realistic_usage_shape_and_reproducibility():
    df1 = generate_realistic_usage(rows=25, seed=7)
    df2 = generate_realistic_usage(rows=25, seed=7)
    assert len(df1) == 25
    assert list(df1["provider"]) == list(df2["provider"])  # seeded -> reproducible
    for col in ["timestamp", "provider", "region", "instance_type", "vcpu_count",
                "avg_cpu_utilization_pct", "vm_hours", "storage_gb", "network_gb",
                "energy_kwh", "carbon", "data_quality"]:
        assert col in df1.columns


def test_generate_realistic_usage_mostly_high_data_quality():
    """Because instance type and region are always drawn from real, resolvable
    tables, almost every generated row should land data_quality == 'high'
    (unlike the old generic-path demo data, which was always 'low')."""
    df = generate_realistic_usage(rows=100, seed=1)
    assert (df["data_quality"] == "high").mean() > 0.8


def test_generate_realistic_usage_utilization_within_bounds():
    df = generate_realistic_usage(rows=100, seed=2)
    assert (df["avg_cpu_utilization_pct"] >= 0).all()
    assert (df["avg_cpu_utilization_pct"] <= 100).all()
    # Real fleet median utilization is low (~8%) -- the generated sample
    # should reflect that shape, not a uniform 50% average.
    assert df["avg_cpu_utilization_pct"].median() < 30


def test_generate_realistic_usage_produces_positive_carbon():
    df = generate_realistic_usage(rows=30, seed=3)
    assert (df["carbon"] > 0).all()
    assert (df["energy_kwh"] > 0).all()


def test_backward_compatible_wrapper_still_works():
    df = generate_fake_usage(rows=5, seed=99)
    assert len(df) == 5
    assert "carbon" in df.columns
