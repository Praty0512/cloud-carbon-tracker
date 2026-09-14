"""Carbon telemetry forecasting -- public API.

This module is a thin façade over two lower-level modules:

* ``ml.features`` -- shared feature engineering, walk-forward CV
  splitting, and the ``ForecastRun``/``CVResult`` result schema.
* ``ml.forecast_models`` -- the actual multi-algorithm model bake-off
  (Ridge, RandomForest, GradientBoosting, XGBoost, LightGBM, SARIMAX, and
  an LSTM, each an optional dependency with graceful degradation), which
  cross-validates every available family with identical walk-forward
  splits and picks the winner by out-of-sample MAE.

Keeping this as a separate façade (rather than merging everything into one
file) means callers -- ``ml/model_registry.py``, ``views/carbon_forecast.py``,
``ml/evaluate_on_reference_dataset.py``, ``ml/train_and_persist.py`` -- get a
stable, small public surface (``build_feature_frame``, ``train_forecast_model``,
``recursive_forecast``, ``ForecastRun``, ``FEATURE_COLUMNS``) regardless of how
many candidate model families get added to the bake-off over time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features import (
    FEATURE_COLUMNS,
    CVResult,
    ForecastRun,
    build_feature_frame,
    build_next_feature_row,
    time_series_splits,
)
from ml.forecast_models import ForecastModelAdapter, available_library_report, run_model_bakeoff

__all__ = [
    "FEATURE_COLUMNS",
    "CVResult",
    "ForecastRun",
    "ForecastModelAdapter",
    "build_feature_frame",
    "build_next_feature_row",
    "time_series_splits",
    "available_library_report",
    "train_forecast_model",
    "recursive_forecast",
]


def train_forecast_model(daily_df: pd.DataFrame) -> tuple[ForecastModelAdapter, ForecastRun]:
    """Run the full model bake-off and return the winning adapter + its report.

    ``daily_df`` is the raw ``(day, carbon)`` daily series -- each candidate
    family builds whatever feature representation it needs internally
    (lag/calendar features for tree/linear models, the raw series for
    SARIMAX, windowed sequences for the LSTM), so callers no longer need to
    build a feature frame themselves before training.
    """
    return run_model_bakeoff(daily_df)


def recursive_forecast(
    daily_df: pd.DataFrame,
    model: ForecastModelAdapter,
    run: ForecastRun,
    horizon: int,
    growth_pct: float,
    reduction_pct: float,
) -> pd.DataFrame:
    """Roll the trained model forward, feeding its own predictions back in as history.

    Works uniformly across every model family via ``model.predict_next()``,
    the one method every ``ForecastModelAdapter`` implements -- this loop
    doesn't need to know whether ``model`` is a tree ensemble, SARIMAX, or
    an LSTM.
    """
    history = daily_df[["day", "carbon"]].copy()
    forecasts: list[dict[str, float | pd.Timestamp]] = []

    for _ in range(horizon):
        next_day = history["day"].max() + pd.Timedelta(days=1)
        predicted = model.predict_next(history)
        predicted = max(predicted, 0.0)
        predicted *= 1 + (growth_pct / 100.0)
        predicted *= 1 - (reduction_pct / 100.0)
        history.loc[len(history)] = {"day": next_day, "carbon": predicted}
        forecasts.append({"day": next_day, "carbon": predicted})

    forecast_df = pd.DataFrame(forecasts)
    low_q, high_q = run.residual_quantiles
    forecast_df["lower_bound"] = np.maximum(forecast_df["carbon"] + low_q, 0.0)
    forecast_df["upper_bound"] = np.maximum(forecast_df["carbon"] + high_q, forecast_df["carbon"])
    return forecast_df
