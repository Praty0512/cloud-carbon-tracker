"""Anomaly detection for carbon telemetry.

The app previously had no way to flag an unexplained emissions spike --
"AI Forecast Studio" only projected forward. This module flags days whose
carbon (or energy) reading is anomalous relative to recent history, so
Operations Center / governance alerting has something concrete to act on
("carbon jumped 3.2x above the seasonal baseline on 2026-03-04" is
actionable; a forecast alone is not).

Uses :class:`sklearn.ensemble.IsolationForest` when available (captures
non-linear, multivariate structure across the same lag/rolling features
used for forecasting) and falls back to a robust modified z-score (median
absolute deviation) when scikit-learn is not installed -- the same
resilience pattern used elsewhere in this project (see
``ml/forecasting.py``, ``main.py``'s optional dotenv import).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest

    _SKLEARN_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    _SKLEARN_AVAILABLE = False


@dataclass
class AnomalyFlag:
    day: pd.Timestamp
    carbon: float
    baseline: float
    deviation_pct: float
    severity: str  # "low" | "medium" | "high"


def _modified_z_scores(values: np.ndarray) -> np.ndarray:
    median = np.median(values)
    mad = np.median(np.abs(values - median)) or 1e-9
    return 0.6745 * (values - median) / mad


def detect_anomalies(daily_df: pd.DataFrame, contamination: float = 0.08) -> pd.DataFrame:
    """Return ``daily_df`` with ``is_anomaly`` and ``anomaly_score`` columns added.

    Requires a ``day``/``carbon`` daily series (the same shape
    :func:`ml.forecasting.build_feature_frame` consumes). Needs at least 10
    points to produce a meaningful signal; shorter series are returned
    unflagged.
    """
    result = daily_df.copy().reset_index(drop=True)
    if len(result) < 10:
        result["is_anomaly"] = False
        result["anomaly_score"] = 0.0
        return result

    rolling_baseline = result["carbon"].rolling(7, min_periods=3).median().bfill()
    rolling_spread = result["carbon"].rolling(7, min_periods=3).std().bfill().replace(0, np.nan)
    deviation = (result["carbon"] - rolling_baseline) / rolling_spread.fillna(rolling_spread.median() or 1.0)

    if _SKLEARN_AVAILABLE:
        features = pd.DataFrame(
            {
                "carbon": result["carbon"],
                "deviation_from_baseline": deviation.fillna(0.0),
                "day_over_day_pct_change": result["carbon"].pct_change().fillna(0.0).replace([np.inf, -np.inf], 0.0),
            }
        )
        model = IsolationForest(contamination=contamination, random_state=0, n_estimators=200)
        predictions = model.fit_predict(features.to_numpy())
        scores = -model.score_samples(features.to_numpy())  # higher = more anomalous
        result["is_anomaly"] = predictions == -1
        result["anomaly_score"] = scores
    else:
        z_scores = _modified_z_scores(result["carbon"].to_numpy(dtype=float))
        result["is_anomaly"] = np.abs(z_scores) > 3.5
        result["anomaly_score"] = np.abs(z_scores) / 3.5

    result["rolling_baseline"] = rolling_baseline
    return result


def summarize_anomalies(flagged_df: pd.DataFrame, max_items: int = 10) -> list[AnomalyFlag]:
    """Turn flagged rows into human-readable anomaly summaries, most severe first."""
    anomalies = flagged_df[flagged_df.get("is_anomaly", False) == True]  # noqa: E712
    if anomalies.empty:
        return []

    flags: list[AnomalyFlag] = []
    for _, row in anomalies.iterrows():
        baseline = float(row.get("rolling_baseline", row["carbon"])) or 1e-9
        deviation_pct = float((row["carbon"] - baseline) / baseline * 100)
        score = float(row.get("anomaly_score", 0.0))
        if score > 1.5 or abs(deviation_pct) > 100:
            severity = "high"
        elif score > 0.8 or abs(deviation_pct) > 40:
            severity = "medium"
        else:
            severity = "low"
        flags.append(
            AnomalyFlag(
                day=row["day"],
                carbon=float(row["carbon"]),
                baseline=baseline,
                deviation_pct=deviation_pct,
                severity=severity,
            )
        )

    flags.sort(key=lambda flag: abs(flag.deviation_pct), reverse=True)
    return flags[:max_items]
