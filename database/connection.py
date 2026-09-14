"""Database connection and table definitions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
)
from sqlalchemy.engine import Connection, Engine

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in minimal local setup
    load_dotenv = None

if load_dotenv:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///carbon_tracker.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine: Engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("full_name", String(255)),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

organizations = Table(
    "organizations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("owner_id", ForeignKey("users.id"), nullable=False),
    Column("plan", String(50), nullable=False, server_default="starter"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

memberships = Table(
    "memberships",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("role", String(50), nullable=False, server_default="owner"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

projects = Table(
    "projects",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("cloud_provider", String(50), nullable=False),
    Column("region", String(100)),
    Column("status", String(50), nullable=False, server_default="active"),
    Column("monthly_budget", Float),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

cloud_accounts = Table(
    "cloud_accounts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("provider", String(50), nullable=False),
    Column("account_name", String(255), nullable=False),
    Column("account_id", String(255), nullable=False),
    Column("region", String(100)),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

usage_data = Table(
    "usage_data",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id")),
    Column("cloud_account_id", ForeignKey("cloud_accounts.id")),
    Column("resource_type", String(100), nullable=False),
    Column("quantity", Float, nullable=False),
    Column("unit", String(50), nullable=False),
    Column("region", String(100), nullable=False),
    Column("cost", Float),
    Column("timestamp", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Added for standardized, real-provider-data ingestion (see
    # engine.standardized_carbon_engine / utils.dataset_adapter). "region"
    # above stays the coarse app bucket for backward compatibility;
    # region_key carries the actual provider region code (e.g. "ap-south-1").
    Column("provider", String(50)),
    Column("region_key", String(100)),
    Column("data_quality", String(20)),
)

carbon_results = Table(
    "carbon_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id")),
    Column("energy_kwh", Float, nullable=False),
    Column("carbon_kg_co2", Float, nullable=False),
    Column("compute_energy", Float),
    Column("storage_energy", Float),
    Column("network_energy", Float),
    Column("region", String(100)),
    Column("timestamp", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # See usage_data above -- same additive, backward-compatible columns so
    # compliance reporting can disclose real region + data-quality tier
    # instead of only the coarse india/us/europe bucket.
    Column("provider", String(50)),
    Column("region_key", String(100)),
    Column("data_quality", String(20)),
)

# GHG Protocol Scope 2 market-based accounting requires evidence of a
# contractual instrument (PPA, supplier-specific factor, or unbundled
# Energy Attribute Certificates/RECs). Previously this app had no way to
# record one at all, so every Scope 2 figure was implicitly location-based
# with no disclosure of that fact. See compliance/ghg_protocol.py.
renewable_energy_contracts = Table(
    "renewable_energy_contracts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("cloud_account_id", ForeignKey("cloud_accounts.id")),
    Column("instrument_type", String(50), nullable=False),  # ppa | supplier_specific | energy_attribute_certificate
    Column("provider", String(50)),
    Column("region_key", String(100)),
    Column("co2e_per_kwh", Float, nullable=False),
    Column("covered_kwh_per_period", Float),
    Column("source", String(255)),
    Column("valid_from", DateTime(timezone=True)),
    Column("valid_to", DateTime(timezone=True)),
    Column("created_by", ForeignKey("users.id")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

recommendations = Table(
    "recommendations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("suggestion", Text, nullable=False),
    Column("carbon_saving_percent", Float),
    Column("cost_impact", Float),
    Column("priority", String(50), nullable=False, server_default="medium"),
    Column("is_implemented", Boolean, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

saved_reports = Table(
    "saved_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("title", String(255), nullable=False),
    Column("report_type", String(100), nullable=False),
    Column("summary", Text),
    Column("payload", JSON),
    Column("created_by", ForeignKey("users.id")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

activity_events = Table(
    "activity_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("user_id", ForeignKey("users.id")),
    Column("event_type", String(100), nullable=False),
    Column("title", String(255), nullable=False),
    Column("description", Text),
    Column("metadata_json", JSON),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

api_keys = Table(
    "api_keys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("key", String(255), unique=True, nullable=False),
    Column("name", String(255), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("last_used", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

data_connectors = Table(
    "data_connectors",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("provider", String(50), nullable=False),
    Column("connector_name", String(255), nullable=False),
    Column("auth_mode", String(100), nullable=False),
    Column("status", String(50), nullable=False, server_default="planned"),
    Column("external_reference", String(255)),
    Column("scope_region", String(100)),
    Column("sync_frequency", String(100)),
    Column("notes", Text),
    Column("metadata_json", JSON),
    Column("last_sync_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

connector_sync_jobs = Table(
    "connector_sync_jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("connector_id", ForeignKey("data_connectors.id"), nullable=False),
    Column("trigger_mode", String(50), nullable=False, server_default="manual"),
    Column("status", String(50), nullable=False, server_default="pending"),
    Column("requested_by", ForeignKey("users.id")),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("payload", JSON),
    Column("worker_notes", Text),
    Column("queued_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("next_run_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("connector_id", ForeignKey("data_connectors.id")),
    Column("source_type", String(100), nullable=False),
    Column("source_name", String(255), nullable=False),
    Column("status", String(50), nullable=False, server_default="completed"),
    Column("records_ingested", Integer, nullable=False, server_default="0"),
    Column("total_carbon_kg_co2", Float, nullable=False, server_default="0"),
    Column("payload", JSON),
    Column("created_by", ForeignKey("users.id")),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("completed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("user_id", ForeignKey("users.id")),
    Column("action", String(150), nullable=False),
    Column("entity_type", String(100), nullable=False),
    Column("entity_id", String(255)),
    Column("severity", String(50), nullable=False, server_default="info"),
    Column("description", Text),
    Column("metadata_json", JSON),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

alerts = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("project_id", ForeignKey("projects.id")),
    Column("title", String(255), nullable=False),
    Column("description", Text),
    Column("severity", String(50), nullable=False, server_default="medium"),
    Column("status", String(50), nullable=False, server_default="open"),
    Column("category", String(100), nullable=False),
    Column("metric_value", Float),
    Column("threshold_value", Float),
    Column("metadata_json", JSON),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

action_items = Table(
    "action_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("alert_id", ForeignKey("alerts.id")),
    Column("recommendation_id", ForeignKey("recommendations.id")),
    Column("title", String(255), nullable=False),
    Column("description", Text),
    Column("owner_user_id", ForeignKey("users.id")),
    Column("status", String(50), nullable=False, server_default="open"),
    Column("priority", String(50), nullable=False, server_default="medium"),
    Column("due_date", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

forecast_models = Table(
    "forecast_models",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("organization_id", ForeignKey("organizations.id"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("source_type", String(100), nullable=False),
    Column("training_rows", Integer, nullable=False, server_default="0"),
    Column("horizon_days", Integer, nullable=False, server_default="30"),
    Column("mae", Float),
    Column("mape", Float),
    Column("residual_std", Float),
    Column("metadata_json", JSON),
    Column("created_by", ForeignKey("users.id")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def _run_additive_migrations() -> None:
    """Add newly-introduced nullable columns to pre-existing SQLite tables.

    ``metadata.create_all()`` only creates tables that don't exist yet; it
    never alters a table that is already on disk. Since this project ships
    a real ``carbon_tracker.db`` that users already have data in, new
    columns (``provider`` / ``region_key`` / ``data_quality`` on
    ``usage_data`` and ``carbon_results``, added for standardized
    multi-cloud ingestion and compliance reporting) need an explicit,
    additive migration rather than silently never appearing. This only
    supports SQLite's ``ALTER TABLE ... ADD COLUMN`` (sufficient for this
    project); a Postgres deployment should run a proper Alembic migration
    instead -- see docs/ROADMAP.md.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    additive_columns = {
        "usage_data": [
            ("provider", "VARCHAR(50)"),
            ("region_key", "VARCHAR(100)"),
            ("data_quality", "VARCHAR(20)"),
        ],
        "carbon_results": [
            ("provider", "VARCHAR(50)"),
            ("region_key", "VARCHAR(100)"),
            ("data_quality", "VARCHAR(20)"),
        ],
    }

    with engine.begin() as connection:
        for table_name, columns in additive_columns.items():
            existing = {
                row[1]  # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            if not existing:
                continue  # table doesn't exist yet -- create_all() will create it with all columns
            for column_name, column_type in columns:
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )


def init_db() -> None:
    """Create all tables, then apply additive migrations for existing databases."""
    metadata.create_all(engine)
    _run_additive_migrations()


@contextmanager
def get_connection() -> Iterator[Connection]:
    """Yield a database connection inside a transaction."""
    with engine.begin() as connection:
        yield connection
