"""Tests for scripts/build_azure_reference_dataset.py's fleet-aggregation math.

These don't touch the 418MB real raw file (that's fetched/cached out of
band, see data/reference_datasets/README.md) -- they build a small
synthetic DataFrame shaped exactly like the real vmtable trace and check
that the vectorized fleet-level formula in the build script is
mathematically identical to calling the real, row-level
engine.standardized_carbon_engine.calculate_standardized_emissions() for
each VM individually. That equivalence is what makes it legitimate to
vectorize a 2.7-million-row real dataset instead of calling the engine
2.7 million times.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from engine.standardized_carbon_engine import calculate_standardized_emissions  # noqa: E402
import build_azure_reference_dataset as build_mod  # noqa: E402


def _synthetic_vmtable_df() -> pd.DataFrame:
    # A handful of VMs with real-looking created/deleted timestamps (seconds
    # into a 30-day trace) and utilization, shaped like the real columns.
    return pd.DataFrame({
        "vm_created_sec": [0, 0, 86400, 172800],
        "vm_deleted_sec": [259200, 2591400, 2591400, 2591400],
        "max_cpu": [50.0, 80.0, 20.0, 99.0],
        "avg_cpu": [12.0, 35.0, 3.0, 60.0],
        "p95_max_cpu": [40.0, 70.0, 15.0, 95.0],
        "category": ["Unknown", "Interactive", "Delay-insensitive", "Unknown"],
        "core_bucket": ["4", "8", "2", "24"],
        "memory_bucket": ["8", "32", "4", "64"],
    })


def test_core_bucket_mapping_covers_open_ended_buckets():
    df = _synthetic_vmtable_df()
    df["vcpu_count"] = df["core_bucket"].astype(str).map(build_mod.CORE_BUCKET_TO_VCPU).fillna(2).astype(int)
    assert list(df["vcpu_count"]) == [4, 8, 2, 24]


def test_daily_fleet_series_matches_row_level_engine_calls():
    df = _synthetic_vmtable_df()
    df["vcpu_count"] = df["core_bucket"].astype(str).map(build_mod.CORE_BUCKET_TO_VCPU).fillna(2).astype(int)

    daily = build_mod._build_daily_fleet_series(df)
    assert len(daily) == build_mod.TRACE_DAYS

    # Day 5: VM 0 (created day0, deleted day3 -> NOT active on day5),
    # VM 1 (created day0, active whole trace -> active),
    # VM 2 (created day1, active whole trace -> active),
    # VM 3 (created day2, active whole trace -> active).
    day5_row = daily.iloc[5]
    assert day5_row["active_vm_count"] == 3

    expected_operational_kg = 0.0
    for idx in [1, 2, 3]:
        result = calculate_standardized_emissions(
            provider="AZURE",
            region_code="East US",
            vcpu_count=int(df.loc[idx, "vcpu_count"]),
            hours=24.0,
            avg_cpu_utilization=float(df.loc[idx, "avg_cpu"]) / 100.0,
            include_embodied=False,
        )
        expected_operational_kg += result.total_carbon_kg

    # The build script rounds output columns to 4 decimal places for a
    # readable CSV; allow for that rounding in the comparison.
    assert day5_row["operational_carbon_kg"] == pytest.approx(expected_operational_kg, abs=5e-5)


def test_daily_fleet_series_is_zero_before_any_vm_created_and_after_all_deleted():
    # A fleet where every VM is created on day 10 and deleted on day 12.
    df = pd.DataFrame({
        "vm_created_sec": [10 * 86400],
        "vm_deleted_sec": [12 * 86400],
        "max_cpu": [50.0], "avg_cpu": [20.0], "p95_max_cpu": [40.0],
        "category": ["Unknown"], "core_bucket": ["4"], "memory_bucket": ["8"],
        "vcpu_count": [4],
    })
    daily = build_mod._build_daily_fleet_series(df)
    assert daily.iloc[0]["active_vm_count"] == 0
    assert daily.iloc[0]["total_carbon_kg"] == 0.0
    assert daily.iloc[11]["active_vm_count"] == 1
    assert daily.iloc[11]["total_carbon_kg"] > 0.0


def test_utilization_profile_percentiles_are_monotonic():
    df = _synthetic_vmtable_df()
    df["vcpu_count"] = df["core_bucket"].astype(str).map(build_mod.CORE_BUCKET_TO_VCPU).fillna(2).astype(int)
    profile = build_mod._build_utilization_profile(df)
    pcts = profile["avg_cpu_utilization_pct"]
    values = [pcts[f"p{p}"] for p in [5, 10, 25, 50, 75, 90, 95, 99]]
    assert values == sorted(values)
