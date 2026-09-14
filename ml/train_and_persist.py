"""Train the forecasting model against the real Azure reference dataset and
persist it to the model registry -- a batch-training entry point suitable
for a scheduled job (cron / CI) in a real deployment, separate from the
on-demand training `views/carbon_forecast.py` does for a specific
organization's own telemetry.

Usage
-----
    python -m ml.train_and_persist
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml.evaluate_on_reference_dataset import load_real_azure_daily_series  # noqa: E402
from ml.forecast_models import available_library_report  # noqa: E402
from ml.model_registry import get_or_train, list_versions  # noqa: E402

REFERENCE_SCOPE = "reference__azure_public_dataset_fleet"


def main() -> None:
    print(f"ML libraries available in this environment: {available_library_report()}")

    daily_df = load_real_azure_daily_series()

    model, run, was_cache_hit = get_or_train(
        REFERENCE_SCOPE,
        daily_df,
        source_description="Real Microsoft Azure Public Dataset fleet daily emissions (30 days, 2.7M VMs)",
    )

    print(f"Cache hit: {was_cache_hit}")
    print(f"Model: {run.model_name} ({run.library})")
    print(f"Bake-off leaderboard (mean CV MAE, lower is better): {run.candidates_tried}")
    print(f"Winning hyperparameters: {run.best_params}")
    print(f"CV MAE: {run.cv_mae:.2f} kg CO2e/day, CV MAPE: {run.cv_mape:.2f}%")
    print(f"Feature importance: {run.feature_importance}")

    versions = list_versions(REFERENCE_SCOPE)
    print(f"\nRegistry now holds {len(versions)} version(s) for scope '{REFERENCE_SCOPE}':")
    for v in versions:
        print(f"  {v['version_id']}  trained_at={v['trained_at']}  data_hash={v['data_hash']}")


if __name__ == "__main__":
    main()
