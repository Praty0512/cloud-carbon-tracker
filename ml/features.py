"""Shared feature engineering, CV splitting, and result schema.

Split out from `ml.forecasting` so that both the public forecasting API
(`ml/forecasting.py`) and the model bake-off implementation
(`ml/forecast_models.py`) can depend on this module without a circular
import between the two.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["index", "lag_1", "lag_3", "lag_7", "rolling_3", "rolling_7", "dow_sin", "dow_cos"]


def build_feature_frame(series_df: pd.DataFrame) -> pd.DataFrame:
    """Create lag and calendar features for a daily carbon time series.

    Used by every tabular (tree/linear) model family in the bake-off.
    Time-series-native families (SARIMAX, the LSTM) work on the raw
    (day, carbon) series directly instead -- they don't need or want this
    lag-feature representation.
    """
    frame = series_df.copy()
    frame["index"] = np.arange(len(frame), dtype=float)
    frame["lag_1"] = frame["carbon"].shift(1)
    frame["lag_3"] = frame["carbon"].shift(3)
    frame["lag_7"] = frame["carbon"].shift(7)
    frame["rolling_3"] = frame["carbon"].rolling(3).mean().shift(1)
    frame["rolling_7"] = frame["carbon"].rolling(7).mean().shift(1)
    frame["dow"] = frame["day"].dt.dayofweek.astype(float)
    frame["dow_sin"] = np.sin(2 * np.pi * frame["dow"] / 7.0)
    frame["dow_cos"] = np.cos(2 * np.pi * frame["dow"] / 7.0)
    return frame.dropna().reset_index(drop=True)


def build_next_feature_row(history_df: pd.DataFrame) -> np.ndarray:
    """The single-row feature vector (FEATURE_COLUMNS order) for the day
    after ``history_df``'s last day. Shared by every tabular model
    adapter's ``predict_next()`` so the recursive-forecast feature
    construction lives in exactly one place."""
    carbon_values = history_df["carbon"].tolist()
    next_day = history_df["day"].max() + pd.Timedelta(days=1)
    lag_1 = carbon_values[-1]
    lag_3 = carbon_values[-3] if len(carbon_values) >= 3 else carbon_values[-1]
    lag_7 = carbon_values[-7] if len(carbon_values) >= 7 else carbon_values[-1]
    rolling_3 = float(np.mean(carbon_values[-3:]))
    rolling_7 = float(np.mean(carbon_values[-7:]))
    dow = float(next_day.dayofweek)
    return np.array([[
        float(len(history_df)),
        float(lag_1),
        float(lag_3),
        float(lag_7),
        float(rolling_3),
        float(rolling_7),
        math.sin(2 * math.pi * dow / 7.0),
        math.cos(2 * math.pi * dow / 7.0),
    ]])


def time_series_splits(n_samples: int, n_splits: int):
    """A minimal, dependency-free walk-forward (expanding-window) split
    generator -- equivalent in spirit to
    ``sklearn.model_selection.TimeSeriesSplit``, implemented locally so
    model families that don't otherwise need scikit-learn at all (SARIMAX,
    the LSTM, the numpy least-squares fallback) aren't forced to import it
    just to get an honest out-of-sample split. Every model family in the
    bake-off uses this same splitter, so their CV scores are directly
    comparable.
    """
    n_splits = max(1, min(n_splits, n_samples - 1)) if n_samples > 1 else 1
    fold_size = n_samples // (n_splits + 1)
    if fold_size < 1:
        split_point = max(1, n_samples - 1)
        yield np.arange(split_point), np.arange(split_point, n_samples)
        return
    produced = False
    for i in range(1, n_splits + 1):
        train_end = fold_size * i
        test_end = fold_size * (i + 1) if i < n_splits else n_samples
        if train_end >= test_end:
            continue
        produced = True
        yield np.arange(train_end), np.arange(train_end, test_end)
    if not produced:
        split_point = max(1, n_samples - 1)
        yield np.arange(split_point), np.arange(split_point, n_samples)


@dataclass
class CVResult:
    """Walk-forward cross-validation results for one candidate model."""

    fold_maes: list[float]
    fold_mapes: list[float]
    fold_residuals: list[float]
    n_splits: int


@dataclass
class ForecastRun:
    """Everything about a trained forecast worth showing to a reviewer."""

    model_name: str
    library: str
    feature_columns: list[str]
    training_rows: int
    cv_folds: int
    cv_mae: float
    cv_mape: float
    fitted_mae: float
    residual_quantiles: tuple[float, float]  # (p10, p90) of backtested residuals
    feature_importance: dict[str, float] = field(default_factory=dict)
    used_sklearn: bool = True
    # The full model-selection leaderboard: {model_name: mean CV MAE}, every
    # family actually available and successfully evaluated in this run --
    # not just the winner. Sorted ascending (best first) when populated.
    candidates_tried: dict[str, float] = field(default_factory=dict)
    # The winning model's tuned hyperparameters (from the randomized search
    # over each family's parameter grid), where applicable.
    best_params: dict = field(default_factory=dict)
