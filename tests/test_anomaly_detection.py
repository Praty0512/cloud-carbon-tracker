"""Tests for ml.anomaly_detection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.anomaly_detection import detect_anomalies, summarize_anomalies


def _series_with_spike(days: int = 60, spike_index: int = 45, spike_size: float = 80.0) -> pd.DataFrame:
    rng = pd.date_range("2026-01-01", periods=days, freq="D")
    np.random.seed(1)
    values = 50 + np.random.normal(0, 2, days)
    values[spike_index] += spike_size
    return pd.DataFrame({"day": rng, "carbon": values})


def test_short_series_returns_unflagged():
    short_series = pd.DataFrame({"day": pd.date_range("2026-01-01", periods=5), "carbon": [1, 2, 3, 4, 5]})
    result = detect_anomalies(short_series)
    assert not result["is_anomaly"].any()


def test_injected_spike_is_detected():
    daily = _series_with_spike()
    flagged = detect_anomalies(daily)
    spike_row = flagged.iloc[45]
    assert bool(spike_row["is_anomaly"]) is True


def test_summarize_anomalies_ranks_by_deviation_and_caps_length():
    daily = _series_with_spike()
    flagged = detect_anomalies(daily)
    summary = summarize_anomalies(flagged, max_items=3)
    assert len(summary) <= 3
    if len(summary) > 1:
        assert abs(summary[0].deviation_pct) >= abs(summary[-1].deviation_pct)
    assert all(item.severity in {"low", "medium", "high"} for item in summary)


def test_no_anomalies_in_flat_series():
    flat = pd.DataFrame({"day": pd.date_range("2026-01-01", periods=20), "carbon": [50.0] * 20})
    flagged = detect_anomalies(flat)
    summary = summarize_anomalies(flagged)
    assert summary == []
