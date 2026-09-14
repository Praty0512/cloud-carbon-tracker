"""Tests for ml.model_registry: cache-or-train persistence semantics."""

from __future__ import annotations

import shutil

import pandas as pd
import pytest

from ml.model_registry import get_or_train, hash_training_series, list_versions


@pytest.fixture()
def isolated_registry(tmp_path, monkeypatch):
    """Point the registry at a throwaway directory so tests never touch the real one."""
    import ml.model_registry as registry_module

    fake_root = tmp_path / "registry"
    monkeypatch.setattr(registry_module, "REGISTRY_ROOT", fake_root)
    yield fake_root
    if fake_root.exists():
        shutil.rmtree(fake_root, ignore_errors=True)


def _synthetic_daily_df(n=40, seed=0) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    days = pd.date_range("2026-01-01", periods=n, freq="D")
    carbon = 100 + rng.normal(0, 5, size=n).cumsum() * 0 + rng.uniform(90, 110, size=n)
    return pd.DataFrame({"day": days, "carbon": carbon})


def test_hash_training_series_is_stable_for_identical_data():
    df1 = _synthetic_daily_df(seed=1)
    df2 = _synthetic_daily_df(seed=1)
    assert hash_training_series(df1) == hash_training_series(df2)


def test_hash_training_series_differs_for_different_data():
    df1 = _synthetic_daily_df(seed=1)
    df2 = _synthetic_daily_df(seed=2)
    assert hash_training_series(df1) != hash_training_series(df2)


def test_get_or_train_trains_on_first_call_and_caches_on_second(isolated_registry):
    daily_df = _synthetic_daily_df()

    model1, run1, hit1 = get_or_train("test_scope", daily_df)
    assert hit1 is False

    model2, run2, hit2 = get_or_train("test_scope", daily_df)
    assert hit2 is True
    assert run2.model_name == run1.model_name
    assert run2.cv_mae == pytest.approx(run1.cv_mae)


def test_get_or_train_retrains_when_data_changes(isolated_registry):
    daily_df_a = _synthetic_daily_df(seed=1)
    daily_df_b = _synthetic_daily_df(seed=2)

    _, _, hit_a = get_or_train("test_scope_2", daily_df_a)
    _, _, hit_b = get_or_train("test_scope_2", daily_df_b)
    assert hit_a is False
    assert hit_b is False  # different data hash -> must retrain, not reuse A's cached model


def test_registry_persists_model_and_metadata_files(isolated_registry):
    daily_df = _synthetic_daily_df()
    get_or_train("test_scope_3", daily_df, source_description="unit test")

    versions = list_versions("test_scope_3")
    assert len(versions) == 1
    assert versions[0]["source_description"] == "unit test"
    assert "forecast_run" in versions[0]

    scope_dir = isolated_registry / "test_scope_3"
    joblib_files = list(scope_dir.glob("*.joblib"))
    assert len(joblib_files) == 1


def test_registry_round_trip_preserves_new_leaderboard_fields(isolated_registry):
    """ForecastRun grew `library`, `candidates_tried`, and `best_params`
    fields for the multi-algorithm bake-off -- a cached run reloaded from
    disk must still carry them, since views/carbon_forecast.py displays
    them directly from a cache-hit run."""
    daily_df = _synthetic_daily_df()
    _, run1, _ = get_or_train("test_scope_4", daily_df)

    _, run2, hit = get_or_train("test_scope_4", daily_df)
    assert hit is True
    assert run2.library == run1.library
    assert run2.candidates_tried == run1.candidates_tried
    assert run2.best_params == run1.best_params
