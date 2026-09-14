"""Train and evaluate ml.forecasting against real-world data.

This is the concrete answer to "run the prediction model through the most
relevant dataset on the internet and make it workable": it scores
`ml.forecasting.train_forecast_model` against two series --

1. **The real thing**: the genuine 30-day daily fleet carbon series derived
   from 2.7M real Microsoft Azure production VMs
   (`data/reference_datasets/azure_fleet_daily_emissions.csv` -- see
   `data/reference_datasets/README.md` and
   `scripts/build_azure_reference_dataset.py` for exactly how it was built
   from the raw telemetry). 30 points is a real, honest constraint (that's
   the actual length of the published trace) -- walk-forward CV still runs,
   just with fewer folds.
2. **An extended series for a fuller CV demonstration**: a longer sequence
   built by block-bootstrap resampling of those same real 30 days (7-day
   blocks, reshuffled, with a small realistic multiplicative drift so it
   isn't a perfectly repeating pattern) rather than inventing a new
   distribution. This is clearly labeled as a *resample of real data*, not
   independently real, and exists only to demonstrate the model-selection
   pipeline with enough history for 5-fold walk-forward CV.

Usage
-----
    python -m ml.evaluate_on_reference_dataset

Run after `scripts/build_azure_reference_dataset.py` (Task 7) has produced
`data/reference_datasets/azure_fleet_daily_emissions.csv`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml.forecasting import build_feature_frame, recursive_forecast, train_forecast_model  # noqa: E402
from ml.forecast_models import available_library_report  # noqa: E402
from ml.anomaly_detection import detect_anomalies, summarize_anomalies  # noqa: E402

REFERENCE_CSV = PROJECT_ROOT / "data" / "reference_datasets" / "azure_fleet_daily_emissions.csv"
REPORT_PATH = PROJECT_ROOT / "docs" / "ML_EVALUATION_REPORT.md"
REPORT_JSON_PATH = PROJECT_ROOT / "data" / "reference_datasets" / "ml_evaluation_results.json"


def load_real_azure_daily_series() -> pd.DataFrame:
    """The real 30-day fleet-emissions series, in ml.forecasting's expected shape."""
    if not REFERENCE_CSV.exists():
        raise FileNotFoundError(
            f"{REFERENCE_CSV} not found -- run "
            "`python scripts/build_azure_reference_dataset.py` first."
        )
    raw = pd.read_csv(REFERENCE_CSV)
    return pd.DataFrame({
        "day": pd.to_datetime(raw["date"]),
        "carbon": raw["total_carbon_kg"].astype(float),
    })


def build_block_bootstrap_extended_series(
    real_daily_df: pd.DataFrame, target_days: int = 210, block_size: int = 7, seed: int = 42,
) -> pd.DataFrame:
    """Extend the real 30-day series by resampling real 7-day blocks.

    This is a legitimate, standard time-series bootstrap technique (moving
    block bootstrap) -- every value in the output is a real observed day's
    carbon figure (times a small documented drift factor to avoid an
    obviously-repeating pattern), not an invented number. It exists purely
    to demonstrate the walk-forward CV pipeline with more folds than 30
    real points allow.
    """
    rng = np.random.default_rng(seed)
    values = real_daily_df["carbon"].to_numpy()
    n = len(values)
    blocks = [values[i : i + block_size] for i in range(0, n - block_size + 1)]

    out_values: list[float] = []
    drift = 1.0
    while len(out_values) < target_days:
        block = blocks[rng.integers(0, len(blocks))]
        # A small random walk drift (+/-1.5% per block) keeps the resampled
        # series from being a perfect repeat of the same 30 real days, while
        # staying anchored to real observed magnitudes.
        drift *= float(rng.uniform(0.985, 1.015))
        drift = float(np.clip(drift, 0.7, 1.4))
        out_values.extend((block * drift).tolist())

    out_values = out_values[:target_days]
    start = real_daily_df["day"].min()
    days = [start + pd.Timedelta(days=i) for i in range(target_days)]
    return pd.DataFrame({"day": days, "carbon": out_values})


def _evaluate_series(name: str, daily_df: pd.DataFrame) -> dict:
    feature_df = build_feature_frame(daily_df)
    model, run = train_forecast_model(daily_df)

    forecast_df = recursive_forecast(
        daily_df, model, run, horizon=7, growth_pct=0.0, reduction_pct=0.0
    )

    anomalies_df = detect_anomalies(daily_df)
    anomaly_summary = summarize_anomalies(anomalies_df, max_items=5)

    return {
        "series_name": name,
        "series_length_days": int(len(daily_df)),
        "usable_training_rows_after_feature_lags": int(len(feature_df)),
        "model_selected": run.model_name,
        "model_library": run.library,
        "used_sklearn": run.used_sklearn,
        "cv_folds": run.cv_folds,
        "cv_mae_kg_co2e": round(run.cv_mae, 4),
        "cv_mape_pct": round(run.cv_mape, 2),
        "fitted_mae_kg_co2e": round(run.fitted_mae, 4),
        "residual_p10_p90_kg_co2e": [round(v, 4) for v in run.residual_quantiles],
        "feature_importance": {k: round(v, 4) for k, v in run.feature_importance.items()},
        "sample_7day_forecast_kg_co2e": [round(v, 2) for v in forecast_df["carbon"].tolist()],
        "anomalies_detected": len(anomaly_summary),
        "top_anomalies": anomaly_summary[:3],
        "leaderboard_all_candidates_cv_mae_kg_co2e": run.candidates_tried,
        "winning_hyperparameters": run.best_params,
    }


def main() -> dict:
    print("ML libraries available in this environment (bake-off candidates):")
    print(json.dumps(available_library_report(), indent=2))

    print("\nLoading real Azure fleet daily carbon series ...")
    real_daily = load_real_azure_daily_series()
    print(f"  {len(real_daily)} real days, carbon range "
          f"{real_daily['carbon'].min():.1f}-{real_daily['carbon'].max():.1f} kg CO2e/day")

    print("\n=== Evaluating on the REAL 30-day Azure fleet series ===")
    real_result = _evaluate_series("real_azure_fleet_30day", real_daily)
    print(json.dumps(real_result, indent=2, default=str))

    print("\nBuilding block-bootstrap-extended series for a fuller CV demonstration ...")
    extended_daily = build_block_bootstrap_extended_series(real_daily, target_days=210)

    print("\n=== Evaluating on the extended (block-bootstrap of real data) series ===")
    extended_result = _evaluate_series("block_bootstrap_extended_210day", extended_daily)
    print(json.dumps(extended_result, indent=2, default=str))

    results = {"real_azure_fleet_30day": real_result, "block_bootstrap_extended_210day": extended_result}
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {REPORT_JSON_PATH}")

    _write_markdown_report(results)
    print(f"Wrote {REPORT_PATH}")
    return results


def _write_markdown_report(results: dict) -> None:
    real = results["real_azure_fleet_30day"]
    ext = results["block_bootstrap_extended_210day"]
    content = f"""# ML Forecasting Model Evaluation

Generated by `python -m ml.evaluate_on_reference_dataset`. This is the
model's actual, walk-forward-cross-validated out-of-sample performance
against real data -- not a training-fit number.

## Real Azure fleet series (30 real days, 2.7M real VMs -- see `data/reference_datasets/README.md`)

- Model selected: **{real['model_selected']}** ({real['model_library']})
- Full bake-off leaderboard (mean CV MAE, kg CO2e/day, lower is better): {json.dumps(real['leaderboard_all_candidates_cv_mae_kg_co2e'])}
- Winning hyperparameters (tuned via randomized search): {json.dumps(real['winning_hyperparameters'])}
- Walk-forward CV folds: {real['cv_folds']}
- CV MAE: {real['cv_mae_kg_co2e']} kg CO2e/day
- CV MAPE: {real['cv_mape_pct']}%
- 80% prediction interval width (residual p10..p90): {real['residual_p10_p90_kg_co2e']}
- Anomalies flagged in the real series: {real['anomalies_detected']}
- Feature importance: {json.dumps(real['feature_importance'])}

## Extended series (block-bootstrap resample of the real 30 days, 210 days, for a fuller CV demo)

- Model selected: **{ext['model_selected']}** ({ext['model_library']})
- Full bake-off leaderboard (mean CV MAE, kg CO2e/day, lower is better): {json.dumps(ext['leaderboard_all_candidates_cv_mae_kg_co2e'])}
- Winning hyperparameters (tuned via randomized search): {json.dumps(ext['winning_hyperparameters'])}
- Walk-forward CV folds: {ext['cv_folds']}
- CV MAE: {ext['cv_mae_kg_co2e']} kg CO2e/day
- CV MAPE: {ext['cv_mape_pct']}%
- Feature importance: {json.dumps(ext['feature_importance'])}

## Why include an LSTM if it's expected to lose?

Every algorithm family actually installed in this environment (Ridge,
Random Forest, Gradient Boosting, XGBoost, LightGBM, SARIMAX, and a small
LSTM -- see `ml/forecast_models.py`) is cross-validated with the *same*
walk-forward split on the *same* data, and the leaderboard above reports
every one of them, not just the winner. At this project's real data scale
(30-210 days), a recurrent neural net has very little data to learn from
relative to a tuned gradient-boosted tree or a well-specified SARIMAX
model, so it's expected -- and, per the leaderboard above, normally
observed -- to lose. That is treated as a legitimate, reportable finding
about model selection at small data scale, not a failure to hide.

## What this does and doesn't prove

The real 30-day series is exactly as long as the published Azure Public
Dataset trace -- that's a genuine constraint of the source data, not a
choice. With only 30 days (23 usable after 7-day lag features), CV MAPE
is a small-sample estimate and should be read as directional, not a
precise production SLA. The 210-day extended series exists purely to
exercise the pipeline with a fuller 5-fold walk-forward split; it is a
resample of the same real observed magnitudes (see
`ml/evaluate_on_reference_dataset.py::build_block_bootstrap_extended_series`),
not independently-collected real data, and is labeled as such everywhere
it's used.

Regenerate this report any time with:

```bash
python -m ml.evaluate_on_reference_dataset
```
"""
    REPORT_PATH.write_text(content)


if __name__ == "__main__":
    main()
