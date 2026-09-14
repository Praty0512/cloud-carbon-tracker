"""A small, file-backed forecasting model registry.

Before this, `views/carbon_forecast.py` called
`ml.forecasting.train_forecast_model()` on every single Streamlit render --
including every time a user nudged the horizon/growth/reduction sliders,
none of which affect training at all. For the walk-forward-CV pipeline
(training multiple candidate models x multiple folds), that's real wasted
compute on every slider tweak.

This module gives trained models a persistent identity: each trained
`(model, ForecastRun)` pair is saved to disk keyed by an organization/source
identifier *and* a content hash of the training series. A caller first asks
the registry for a model matching the current data's hash; only on a miss
(new/changed data) does it actually retrain and then persist the result.
This is also what makes model persistence meaningful for a real deployment
-- a scheduled batch job could train once and every web worker process
loads the same artifact from disk rather than each refitting independently.

Layout on disk (git-ignored, see .gitignore -- these are runtime artifacts,
not source):

    models/registry/<scope_key>/<version_id>.joblib   (the fitted model object)
    models/registry/<scope_key>/<version_id>.json      (ForecastRun + provenance)
    models/registry/<scope_key>/latest.json             (pointer to the current version_id)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from ml.forecasting import ForecastRun

REGISTRY_ROOT = Path(__file__).parent.parent / "models" / "registry"

# Keep the most recent N trained versions per scope; older ones are pruned
# on save so the registry doesn't grow unbounded across a long-running app.
MAX_VERSIONS_PER_SCOPE = 5


def _safe_scope_key(scope_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(scope_key))[:200] or "default"


def hash_training_series(daily_df: pd.DataFrame) -> str:
    """A stable content hash of the daily (day, carbon) series used to train.

    Two calls with the same underlying data (same days, same carbon values)
    produce the same hash regardless of dataframe index/object identity, so
    the registry can tell "data hasn't changed, sliders were just moved"
    apart from "new data was uploaded, must retrain."
    """
    payload = daily_df[["day", "carbon"]].copy()
    payload["day"] = pd.to_datetime(payload["day"]).astype("int64")
    digest = hashlib.sha256(payload.to_csv(index=False).encode("utf-8")).hexdigest()
    return digest[:16]


def _scope_dir(scope_key: str) -> Path:
    return REGISTRY_ROOT / _safe_scope_key(scope_key)


def load_if_current(scope_key: str, data_hash: str) -> tuple[object, ForecastRun] | None:
    """Return (model, run) from the registry only if it was trained on this exact data hash."""
    pointer_path = _scope_dir(scope_key) / "latest.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if pointer.get("data_hash") != data_hash:
        return None

    version_id = pointer.get("version_id")
    scope_dir = _scope_dir(scope_key)
    model_path = scope_dir / f"{version_id}.joblib"
    meta_path = scope_dir / f"{version_id}.json"
    if not model_path.exists() or not meta_path.exists():
        return None

    try:
        model = joblib.load(model_path)
        meta = json.loads(meta_path.read_text())
        run = ForecastRun(**meta["forecast_run"])
    except Exception:
        # A corrupted or version-mismatched cache entry should never break
        # forecasting -- fall through to a fresh train.
        return None
    return model, run


def save_version(
    scope_key: str, data_hash: str, model: object, run: ForecastRun, *, source_description: str = "",
) -> str:
    """Persist a freshly-trained model as the current version for this scope. Returns version_id."""
    scope_dir = _scope_dir(scope_key)
    scope_dir.mkdir(parents=True, exist_ok=True)

    trained_at = datetime.now(timezone.utc)
    version_id = f"{trained_at.strftime('%Y%m%dT%H%M%S')}_{data_hash}"

    joblib.dump(model, scope_dir / f"{version_id}.joblib")
    meta = {
        "version_id": version_id,
        "scope_key": scope_key,
        "data_hash": data_hash,
        "trained_at": trained_at.isoformat(),
        "source_description": source_description,
        "forecast_run": asdict(run),
    }
    (scope_dir / f"{version_id}.json").write_text(json.dumps(meta, indent=2, default=str))
    (scope_dir / "latest.json").write_text(json.dumps({"version_id": version_id, "data_hash": data_hash}, indent=2))

    _prune_old_versions(scope_dir, keep_version_id=version_id)
    return version_id


def _prune_old_versions(scope_dir: Path, keep_version_id: str) -> None:
    metas = sorted(scope_dir.glob("*.json"))
    version_ids = sorted(
        {p.stem for p in metas if p.stem != "latest"},
    )
    if len(version_ids) <= MAX_VERSIONS_PER_SCOPE:
        return
    to_remove = [v for v in version_ids if v != keep_version_id][: len(version_ids) - MAX_VERSIONS_PER_SCOPE]
    for version_id in to_remove:
        for suffix in (".joblib", ".json"):
            path = scope_dir / f"{version_id}{suffix}"
            if path.exists():
                path.unlink()


def list_versions(scope_key: str) -> list[dict]:
    """Metadata for every retained version in a scope, most recent first."""
    scope_dir = _scope_dir(scope_key)
    if not scope_dir.exists():
        return []
    versions = []
    for meta_path in scope_dir.glob("*.json"):
        if meta_path.stem == "latest":
            continue
        try:
            versions.append(json.loads(meta_path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    versions.sort(key=lambda v: v.get("trained_at", ""), reverse=True)
    return versions


def get_or_train(
    scope_key: str,
    daily_df: pd.DataFrame,
    *,
    source_description: str = "",
) -> tuple[object, ForecastRun, bool]:
    """Return (model, run, was_cache_hit). Trains and persists only on a miss.

    This is the function views/carbon_forecast.py calls instead of
    ml.forecasting.train_forecast_model() directly -- it's a drop-in
    superset that adds the registry cache/persist behavior. Training now
    runs the full multi-algorithm bake-off (ml.forecast_models), which
    builds whatever feature representation each candidate family needs
    internally, so callers only need to supply the raw daily series.
    """
    from ml.forecasting import train_forecast_model  # local import avoids a cycle at module load

    data_hash = hash_training_series(daily_df)
    cached = load_if_current(scope_key, data_hash)
    if cached is not None:
        return cached[0], cached[1], True

    model, run = train_forecast_model(daily_df)
    save_version(scope_key, data_hash, model, run, source_description=source_description)
    return model, run, False
