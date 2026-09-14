"""Tests for ml.evaluate_on_reference_dataset: the real-data training/eval pipeline."""

from __future__ import annotations

import pandas as pd
import pytest

from ml.evaluate_on_reference_dataset import (
    REFERENCE_CSV,
    build_block_bootstrap_extended_series,
    load_real_azure_daily_series,
)

pytestmark = pytest.mark.skipif(
    not REFERENCE_CSV.exists(),
    reason="data/reference_datasets/azure_fleet_daily_emissions.csv not built in this environment "
    "(run scripts/build_azure_reference_dataset.py, which downloads the real Azure Public Dataset)",
)


def test_load_real_azure_daily_series_shape():
    df = load_real_azure_daily_series()
    assert len(df) == 30
    assert set(df.columns) == {"day", "carbon"}
    assert (df["carbon"] > 0).all()
    assert pd.api.types.is_datetime64_any_dtype(df["day"])


def test_block_bootstrap_extends_series_and_stays_near_real_magnitude():
    real_df = load_real_azure_daily_series()
    extended = build_block_bootstrap_extended_series(real_df, target_days=100, seed=1)
    assert len(extended) == 100
    # The resample applies a bounded drift (0.7x-1.4x of the real block it
    # was drawn from) -- so the extended series should stay within a
    # generous multiple of the real series' observed range, not diverge
    # arbitrarily the way an unconstrained synthetic generator could.
    assert extended["carbon"].min() > real_df["carbon"].min() * 0.5
    assert extended["carbon"].max() < real_df["carbon"].max() * 1.6


def test_block_bootstrap_is_reproducible_with_seed():
    real_df = load_real_azure_daily_series()
    a = build_block_bootstrap_extended_series(real_df, target_days=50, seed=5)
    b = build_block_bootstrap_extended_series(real_df, target_days=50, seed=5)
    assert list(a["carbon"]) == list(b["carbon"])
