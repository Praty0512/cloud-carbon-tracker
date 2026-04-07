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

- 📊 Carbon emission tracking from cloud usage data
- 🌍 Region-based carbon intensity analysis
- 📈 Forecasting of future emissions
- 🧠 Optimization recommendations
- 🏢 Multi-tenant SaaS workspace for teams

---

## ✨ Key Features

- 🔐 **Multi-tenant architecture** (organizations, teams, roles)
- 📂 **Dataset upload & normalization**
- ☁️ **Multi-cloud support** (AWS, GCP, Azure – connector-ready)
- 🧮 **Carbon calculation engine**
- 📊 **Interactive dashboards & scorecards**
- 📈 **Forecasting & trend analysis**
- 🧾 **Governance & audit tracking**
- ⚙️ **Background job scheduling (connector sync)**

---

## 🏗️ Architecture Overview

Streamlit UI (Frontend)
↓
FastAPI Backend (API Layer)
↓
Engine Layer (Carbon, Forecasting, Recommendations)
↓
Database (SQLite / PostgreSQL)

---

## 🛠️ Tech Stack

- **Frontend:** Streamlit
- **Backend:** FastAPI
- **Database:** PostgreSQL / SQLite
- **ORM:** SQLAlchemy
- **Data Processing:** Pandas, NumPy
- **Visualization:** Plotly

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

4. Run the application

Frontend (Streamlit):

streamlit run app.py
Backend (FastAPI):

uvicorn main:app --reload

5. Run background scheduler (optional)
   python -m engine.sync_scheduler

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
No real-time cloud API integration (uses mock/connectors)
Basic forecasting model
Streamlit UI not optimized for large-scale production

🚀 Future Improvements
Real cloud billing API integration (AWS, GCP, Azure)
JWT/OAuth authentication
Role-based access control (RBAC)
Docker + cloud deployment
Advanced ML-based forecasting
Real-time monitoring and alerts

🎯 Project Goal

To build a scalable SaaS platform that helps organizations make
data-driven, sustainable cloud decisions.
