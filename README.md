# 🌍 Cloud Carbon Tracker

Cloud Carbon Tracker is a **SaaS platform for carbon-aware cloud operations**.  
It enables organizations to track, analyze, and optimize the carbon footprint of their cloud infrastructure across multiple providers.

---

## 🚀 Problem Statement

Cloud computing is growing rapidly, but most organizations:

- ❌ Do not track the carbon impact of their infrastructure
- ❌ Lack visibility into region-based emissions
- ❌ Cannot optimize workloads for sustainability

This leads to **hidden environmental costs and inefficient resource usage**.

---

## 💡 Solution

Cloud Carbon Tracker provides:

- 📊 Carbon emission tracking from real AWS/GCP/Azure billing & usage data
- 🌍 Region-based carbon intensity analysis using sourced grid factors (EPA eGRID, EEA, Google, EMA Singapore)
- 📈 Cross-validated ML forecasting of future emissions, with anomaly detection
- 🧠 Quantified optimization recommendations (real kg CO2 deltas, not qualitative tips)
- 🧾 GHG Protocol / ISO 14064-1 / CSRD-ESRS E1 aligned compliance reporting
- 🏢 Multi-tenant SaaS workspace for teams

---

## ✨ Key Features

- 🔐 **Multi-tenant architecture** (organizations, teams, roles)
- 📂 **Dataset upload & normalization**, with a per-record data-quality tier
- ☁️ **Multi-cloud support** (AWS CUR, GCP billing export, Azure Cost Management export — all three actually parsed, not just AWS/GCP)
- 🧮 **Standardized carbon calculation engine** (Cloud Carbon Footprint methodology: per-vCPU wattage curves, provider PUE, sourced regional grid intensity, optional SCI-spec embodied carbon) — see `docs/CARBON_METHODOLOGY.md`
- 📊 **Interactive dashboards & scorecards**
- 📈 **ML forecasting & anomaly detection** — a genuine multi-algorithm "bake-off" (Ridge, Random Forest, Gradient Boosting, XGBoost, LightGBM, a SARIMAX classical time-series baseline, and a small LSTM, each an optional dependency), every candidate walk-forward cross-validated on the *same* splits so the winner is picked by honest out-of-sample error, with hyperparameter tuning, explainability, backtested prediction intervals, and the full leaderboard surfaced in the UI — validated against real Microsoft Azure production telemetry, see `docs/ML_EVALUATION_REPORT.md` — see `ml/forecast_models.py`
- 💾 **Persistent model registry** (`ml/model_registry.py`) — trained forecast models are cached by a content hash of the training data, so re-rendering the forecast page doesn't silently retrain from scratch
- 🧾 **Governance & compliance reporting**, standards-mapped (GHG Protocol, ISO 14064-1:2018, CSRD/ESRS E1, GRI 305) — see `docs/COMPLIANCE_MAPPING.md`
- 🌱 **GHG Protocol Scope 2 dual reporting** (location-based & market-based, with renewable energy contract tracking) — see `compliance/ghg_protocol.py`
- ⚙️ **Background job scheduling (connector sync)**
- ✅ **Automated tests** (`pytest`, 80+ tests) for the standardization, ML (including per-algorithm and model-persistence coverage), compliance, and reference-dataset modules
- 🐳 **Docker + CI** — `Dockerfile` / `docker-compose.yml` (app + api + Postgres) and `.github/workflows/ci.yml` (pytest + ruff on every push)
- 📝 **Structured JSON logging** (`utils/logging_config.py`), wired into the connector sync path

---

## 🏗️ Architecture Overview

Streamlit UI (Frontend)
↓
FastAPI Backend (API Layer)
↓
Engine Layer (`engine/` standardized carbon calc, `ml/` forecasting & anomaly detection, `compliance/` GHG Protocol & standards reporting)
↓
Database (SQLite / PostgreSQL)

See `docs/CARBON_METHODOLOGY.md`, `docs/COMPLIANCE_MAPPING.md`, and
`docs/ROADMAP.md` for the full technical writeup of each layer and what's
next.

---

## 🛠️ Tech Stack

- **Frontend:** Streamlit
- **Backend:** FastAPI
- **Database:** PostgreSQL / SQLite
- **ORM:** SQLAlchemy
- **Data Processing:** Pandas, NumPy
- **ML:** a 7-algorithm forecasting bake-off -- scikit-learn (Ridge, Random Forest, Gradient Boosting), XGBoost, LightGBM, statsmodels (SARIMAX), and PyTorch (a small LSTM) -- each an optional dependency, cross-validated identically and compared honestly by out-of-sample MAE (see `ml/forecast_models.py`), plus IsolationForest anomaly detection; falls all the way back to a pure-numpy least-squares fit if none of the above are installed
- **Visualization:** Plotly
- **Testing:** pytest (`tests/`)

---

## ⚙️ Setup Instructions

### 1. Create virtual environment

powershell
python -m venv .saas-venv --system-site-packages
.\.saas-venv\Scripts\Activate.ps1
pip install -r requirements.txt

2. Configure environment variables

Copy .env.example → .env and update:

DATABASE_URL
SECRET_KEY

3. Initialize database
   python init_db.py
   (safe to re-run on an existing database — it only adds new columns/tables, never drops data)

4. Run the application

Frontend (Streamlit):

streamlit run app.py
Backend (FastAPI):

uvicorn main:app --reload

5. Run background scheduler (optional)
   python -m engine.sync_scheduler

6. Run the test suite (optional)
   pytest

7. Build the real-world ML reference dataset (optional, ~450MB download)
   python scripts/build_azure_reference_dataset.py
   python -m ml.evaluate_on_reference_dataset
   python -m ml.train_and_persist
   (see data/reference_datasets/README.md and docs/ML_EVALUATION_REPORT.md)

### Docker

powershell
cp .env.example .env   # fill in ENCRYPTION_KEY / SECRET_KEY / STREAMLIT_SESSION_SECRET
docker compose up --build
(Streamlit UI on :8501, FastAPI on :8000, Postgres on :5432. See docker-compose.yml.)

🗄️ Database Configuration
Local: sqlite:///./carbon_tracker.db
Production: PostgreSQL (recommended)
Suggested host: Supabase

📊 Example Workflow
User logs into workspace
Uploads cloud usage dataset
System normalizes and stores data
Carbon emissions are calculated
Dashboard visualizes insights
Forecasts and recommendations are generated

⚠️ Current Limitations
No live cloud billing API pull yet — connectors read a configured CSV/S3/GCS/Blob export path (AWS CUR, GCP billing export, Azure Cost Management export are all parsed), rather than calling the Cost Explorer / BigQuery billing / Cost Management APIs directly
Grid carbon intensity is annual-average, not real-time/marginal (see docs/CARBON_METHODOLOGY.md)
Market-based Scope 2 reporting requires manually recording a renewable energy contract; no UI for that yet (backend already exists — see docs/ROADMAP.md Phase 2)
Streamlit UI not optimized for large-scale production

🚀 Future Improvements
See docs/ROADMAP.md for the full, current phased plan. Highlights:
Renewable energy contract UI (closes the Scope 2 market-based gap)
Live cloud billing API integration (AWS, GCP, Azure), not just export-file parsing
Real-time/marginal grid carbon intensity (Electricity Maps / WattTime)
Per-instance-family embodied carbon (Boavizta API)
Alembic migrations for Postgres, auth hardening, API rate limiting (Docker/CI/logging already shipped -- see docs/ROADMAP.md Phase 1.5)

🎯 Project Goal

To build a scalable SaaS platform that helps organizations make
data-driven, sustainable cloud decisions.
