# Roadmap: Cloud Carbon Tracker -> A Production-Credible Platform

This is the working plan for turning Cloud Carbon Tracker from a
well-structured demo into a platform whose numbers and compliance posture
would survive scrutiny from a real FinOps/sustainability team. It's
organized in phases; each phase builds on the last and is scoped to be
independently shippable.

## Phase 0 — Baseline audit (done, this session)

What was actually wrong with the "standardized for real AWS/GCP/Azure
data" and "compliant with international rules" claims before this pass:

- Every emission constant (`COMPUTE_FACTOR`, `STORAGE_FACTOR`,
  `NETWORK_FACTOR`, the region "intensity" table) was invented for the
  demo, not sourced from anything.
- AWS/GCP CUR ingestion computed carbon as `vm_hours * 0.42` — no
  instance size, no real region factor.
- Azure had no billing-export parser at all; "multi-cloud support" for
  Azure was aspirational.
- The forecasting model was fit once against its own training data with
  no validation split, and its "confidence band" was a fixed
  `residual_std * 1.28` heuristic, not backtested.
- There was no anomaly detection.
- The recommendation engine was four hard-coded sentences with no number
  behind any of them.
- "Governance Center" had a control matrix with no reference to any real
  standard, graded against invented thresholds.
- No renewable-energy/market-based accounting concept existed at all, so
  every carbon figure was implicitly (and silently) location-based.
- No tests.

## Phase 1 — Standardization, ML, and compliance foundation (done, this session)

- **`engine/emission_factors.py` + `engine/standardized_carbon_engine.py`**:
  Cloud Carbon Footprint methodology (per-vCPU wattage curves, provider
  PUE, SCI-spec embodied carbon) with real, sourced regional grid factors
  per actual AWS/GCP/Azure region code
  (`data/grid_emissions_{aws,gcp,azure}.json`, EPA eGRID / EEA / Google /
  EMA Singapore / carbonfootprint.com). See `docs/CARBON_METHODOLOGY.md`.
- **`utils/dataset_adapter.py`**: AWS CUR and GCP billing normalization
  rewired onto the standardized engine (instance-type-aware, region-aware);
  new `normalize_azure_cost_export_dataframe()` — Azure ingestion didn't
  exist before. Every normalized row now carries a `data_quality` tier.
- **`ml/forecasting.py`**: walk-forward cross-validated model selection
  (Ridge / RandomForest / GradientBoosting via scikit-learn, numpy
  least-squares fallback), out-of-sample error reporting, residual-quantile
  prediction intervals, feature importances for explainability.
- **`ml/anomaly_detection.py`**: IsolationForest-based (MAD fallback)
  emissions anomaly flagging, wired into AI Forecast Studio.
- **`ml/optimization_recommender.py`**: quantified region-migration and
  right-sizing recommendations backed by the standardized engine (real kg
  CO2 deltas, not qualitative tips).
- **`compliance/ghg_protocol.py` + `compliance/reporting.py`**: GHG
  Protocol Scope 2 dual reporting (location-based / market-based), a
  standards-mapped control checklist (GHG Protocol, ISO 14064-1:2018,
  CSRD/ESRS E1, GRI 305) replacing the old invented control matrix. See
  `docs/COMPLIANCE_MAPPING.md`.
- **Database**: additive, auto-migrating schema changes
  (`provider`/`region_key`/`data_quality` on `usage_data` and
  `carbon_results`; new `renewable_energy_contracts` table +
  `RenewableContractService`) so existing databases upgrade safely.
- **Tests**: `tests/` covering the new engine, ingestion, ML, and
  compliance modules (47 tests as of this writing).

## Phase 1.5 — Real-data validation, ML training pipeline, and productionization (done, this session)

- **Found and fixed a real bug via real-data validation**: cross-checking
  the standardized engine against genuine Azure production telemetry
  surfaced a 1000x unit error in `data/grid_emissions_{aws,gcp,azure}.json`
  (source CCF coefficients are metric tons CO2e/kWh, not kg as this project
  had assumed). Fixed across all 94 regions; regression-tested in
  `tests/test_emission_factors.py`.
- **`scripts/build_azure_reference_dataset.py` + `data/reference_datasets/`**:
  a real, sourced benchmark dataset built from the Microsoft Azure Public
  Dataset (2.7M real production VMs, 30-day trace) -- a genuine daily fleet
  carbon series computed by the standardized engine, plus an empirical
  CPU-utilization/instance-size profile. See
  `data/reference_datasets/README.md`.
- **`utils/demo_data.py`**: demo/onboarding dataset generation now samples
  from that real empirical profile instead of arbitrary numbers (the old
  `utils/fake_data_generator.py` is now a thin wrapper over it), and lands
  `data_quality = "high"` like a real billing export would, not `"low"`.
- **`ml/evaluate_on_reference_dataset.py`**: trains and walk-forward
  cross-validates `ml/forecasting.py` against the real 30-day Azure series
  (plus a block-bootstrap-extended series for a fuller CV demo), and writes
  `docs/ML_EVALUATION_REPORT.md` with the actual out-of-sample numbers.
- **`ml/model_registry.py` + `ml/train_and_persist.py`**: file-backed model
  persistence keyed by a content hash of the training series -- fixes a
  real perf bug where every Streamlit slider tweak in AI Forecast Studio
  was silently retraining the entire model-selection pipeline from
  scratch; `views/carbon_forecast.py` now reuses a persisted model when the
  underlying data hasn't changed.
- **Production hardening (Phase 3 items, pulled forward)**: `Dockerfile` +
  `docker-compose.yml` (app + api + Postgres), `.github/workflows/ci.yml`
  (pytest + ruff, on every push/PR), `.env.example`, structured JSON
  logging (`utils/logging_config.py`, wired into the connector sync path
  which is this app's one unattended/scheduled execution path).

## Phase 1.6 — A genuine multi-algorithm forecasting bake-off (done, this session)

Phase 1's forecasting pipeline already did walk-forward CV model selection
across three scikit-learn candidates. This phase turns that into a real
bake-off across the algorithm families that actually matter for tabular and
time-series forecasting, so the model that wins is a checkable, honest
finding rather than a foregone conclusion:

- **`ml/features.py`** (new): the shared feature engineering
  (`build_feature_frame`, `build_next_feature_row`), a dependency-free
  walk-forward `time_series_splits()` generator (so non-sklearn candidates
  don't need to import scikit-learn just to get an honest split), and the
  `ForecastRun`/`CVResult` schema -- extracted so it can be shared between
  the public API and the model implementations without a circular import.
- **`ml/forecast_models.py`** (new): a common `ForecastModelAdapter`
  interface (`fit` / `predict_next` / `cv_evaluate` / `feature_importance`)
  implemented by seven candidate families, each an optional dependency with
  graceful degradation if not installed: **Ridge**, **Random Forest**,
  **Gradient Boosting** (scikit-learn, carried over from Phase 1), plus
  **XGBoost** and **LightGBM** (the two gradient-boosting implementations
  that actually win most real-world tabular competitions), a **SARIMAX**
  classical time-series baseline (statsmodels, fit on the raw series rather
  than lag features), and a small **LSTM** (PyTorch, windowed
  sequence-to-one regression) included deliberately for algorithmic
  breadth even though it's expected to lose at this project's small real
  data scale. Every family is cross-validated with the *same* walk-forward
  split on the *same* data (tree/linear models are also hyperparameter-tuned
  via `RandomizedSearchCV` first), and the full leaderboard --
  `ForecastRun.candidates_tried` -- is kept, not just the winner.
- **`ml/forecasting.py`**: now a thin public façade over the two modules
  above (`train_forecast_model(daily_df)` runs the bake-off;
  `recursive_forecast()` rolls the winner forward via the adapter
  interface's `predict_next()`, so it works identically regardless of which
  family won).
- **`views/carbon_forecast.py`**: AI Forecast Studio now shows the full
  bake-off leaderboard (every candidate's CV MAE, ranked), the winning
  model's library and tuned hyperparameters, and which optional ML
  libraries aren't installed in the current environment (and therefore
  skipped from the comparison) -- so the multi-algorithm comparison is
  actually visible, not just a silently-picked winner.
- **Real-data result** (`docs/ML_EVALUATION_REPORT.md`, regenerated by
  `python -m ml.evaluate_on_reference_dataset`): against the real 30-day
  Azure fleet series, **Random Forest** wins (CV MAE 503 kg CO2e/day), with
  the **LSTM** a close second (535) and Gradient Boosting third (554);
  Ridge, LightGBM, SARIMAX, and XGBoost trail behind. That the LSTM doesn't
  win despite genuine training is itself the documented, honest finding
  this phase set out to produce: at a few dozen to a few hundred data
  points, a recurrent net has too little data to beat a well-tuned tree
  ensemble.
- **Found and fixed during real-data validation**: an early, small
  walk-forward CV fold combined with a seasonal SARIMAX order occasionally
  produced a numerically unstable forecast (one fold's MAE in the
  thousands next to single digits on every other fold) that would have
  unfairly tanked that candidate's score. Fixed with a per-fold minimum
  training-size check for the seasonal term plus a sanity clamp that falls
  back to naive persistence for that fold rather than letting an unstable
  extrapolation into the leaderboard (`SARIMAXForecastModel.cv_evaluate` in
  `ml/forecast_models.py`).
- **Tests**: `tests/test_forecasting.py` and `tests/test_model_registry.py`
  rewritten for the new API, with new coverage for the leaderboard actually
  containing every installed family, `recursive_forecast` working correctly
  regardless of which adapter type wins, and -- important for the model
  registry's `joblib`-based persistence -- every adapter type (including
  the tree ensembles, SARIMAX, and the LSTM) surviving a real dump/load
  round trip (80 tests total, up from 65).

## Phase 2 — Close the gaps Phase 1 disclosed rather than hid

These are the specific "Partial" items the new Governance Center control
matrix will show until addressed:

1. **Renewable energy contract UI.** The backend
   (`RenewableContractService`, `renewable_energy_contracts` table,
   `compliance.ghg_protocol.scope2_dual_report()`) already supports
   PPAs/RECs/supplier-specific factors — there's no screen in Integrations
   Hub to record one yet. This is the single highest-leverage next step:
   it's what turns "market-based Scope 2" from a documented fallback into
   a real, differentiated number.
2. **Real-time/marginal grid factors.** Current factors are annual
   averages. Integrate Electricity Maps or WattTime for time-of-use
   carbon intensity, which is what actually enables carbon-aware
   scheduling recommendations ("run this batch job at 2am UTC when the
   grid is cleaner").
3. **Per-instance-family embodied carbon.** Replace the single 1500kg
   reference-server default with a Boavizta API lookup per instance
   family, matching CCF's own approach.
4. **Live billing API pull.** Connectors currently execute against a
   locally-configured CSV/S3/GCS/Blob export path. Wiring
   `engine/connector_worker.py` to call the AWS Cost Explorer API, GCP
   BigQuery billing export query, and Azure Cost Management API directly
   (OAuth/IAM-based, not just a static export file) removes the manual
   export step entirely.
5. **Scope 3 category assessment.** Formally document which GHG Protocol
   Scope 3 categories are and aren't covered (this tool's boundary is
   cloud compute/storage/network; broader purchased-goods-and-services
   Scope 3 is out of scope) so a real inventory built on this tool knows
   exactly what else it needs.

## Phase 3 — Productionization ("a proper project")

Independent of the carbon/ML/compliance work, these are the gaps between
"a strong portfolio project" and "a project a team could actually run":

1. ~~**CI.**~~ **Done (Phase 1.5).** `.github/workflows/ci.yml` runs
   `pytest` and `ruff` on every push/PR, plus a Docker build check. mypy is
   wired in as `continue-on-error` (not yet a hard gate -- the codebase
   predates type annotations in most modules; tightening this
   incrementally is still open).
2. **Auth hardening.** `api/routes/auth.py` uses JWT via `python-jose`;
   confirm refresh-token handling, password reset flow, and rate limiting
   exist or are added. Audit `utils/encryption.py`'s Fernet key handling
   for production key rotation. *(Not done this session.)*
3. **Postgres migration path.** `database/connection.py`'s new additive
   migration helper is SQLite-only (see its docstring) — a Postgres
   deployment needs a real Alembic migration for the same schema changes.
   *(`docker-compose.yml` now runs the app against real Postgres, which
   will surface whether `metadata.create_all()` alone is sufficient for a
   first deploy -- but ongoing schema changes to an existing Postgres
   database still need real Alembic migrations, not yet added.)*
4. ~~**Structured logging & observability.**~~ **Partially done (Phase
   1.5).** `utils/logging_config.py` (JSON logs, `LOG_LEVEL`/`LOG_FORMAT`
   env config) is wired into `engine/connector_worker.py` (job
   start/finish/failure events) and `main.py` startup. Basic metrics
   (sync success/failure *rate* over time, not just per-event logs) are
   still open.
5. **Rate limiting & pagination on `/api/*` routes.** *(Not done this
   session.)*
6. ~~**Docker + deployment.**~~ **Done (Phase 1.5).** `Dockerfile` +
   `docker-compose.yml` (app + api + Postgres). Not yet tested against a
   live Docker daemon in this environment (the sandbox this was built in
   has no daemon running) — validate with `docker compose up` before
   relying on it for a real deployment.
7. ~~**Secrets management.**~~ **Documented (Phase 1.5).** `.env.example`
   lists every required secret (`ENCRYPTION_KEY`, `SECRET_KEY`,
   `STREAMLIT_SESSION_SECRET`, `DATABASE_URL`) with generation commands;
   `docker-compose.yml` fails fast (`${VAR:?...}`) if they're unset rather
   than silently running on insecure defaults. Actual rotation tooling/
   schedule is still a deployment-specific decision, not implemented here.

## How to pick up from here

Two natural next sessions, in priority order:

1. **Phase 2 item 1 (renewable contract UI)**: the entire backend for it
   already exists (`RenewableContractService`), so it's a pure UI task — a
   form in Integrations Hub, and a small addition to Governance
   Center/AI Forecast Studio to surface market-based numbers next to
   location-based ones.
2. **Validate the Docker/Postgres stack against a real daemon**
   (`docker compose up`, confirm `init_db()` behaves correctly against a
   fresh Postgres database, confirm the Streamlit and FastAPI containers
   both come up healthy) — this was built and reasoned through carefully
   this session but could not be executed end-to-end in the sandbox it was
   authored in.
