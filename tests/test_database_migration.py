"""Tests for the additive SQLite migration in database.connection.init_db().

Verifies that a pre-existing database (simulating a user's real
carbon_tracker.db from before this change) gets the new provider /
region_key / data_quality columns added without losing existing rows, and
that the new renewable_energy_contracts table is created.
"""

from __future__ import annotations

import sqlite3


def test_migration_adds_columns_and_preserves_existing_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"

    # Simulate a pre-existing database with the OLD schema (no new columns).
    connection = sqlite3.connect(str(db_path))
    connection.executescript(
        """
        CREATE TABLE carbon_results (
            id INTEGER PRIMARY KEY,
            organization_id INTEGER,
            energy_kwh FLOAT,
            carbon_kg_co2 FLOAT,
            region VARCHAR(100)
        );
        CREATE TABLE usage_data (
            id INTEGER PRIMARY KEY,
            organization_id INTEGER,
            region VARCHAR(100)
        );
        INSERT INTO carbon_results (id, organization_id, energy_kwh, carbon_kg_co2, region)
        VALUES (1, 1, 10.0, 2.0, 'india');
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ENCRYPTION_KEY", "4P-rbUjRKWXL9dFWq_mJRVI3rE7IYEfjgZbp1JjRk_o=")

    import importlib

    import database.connection as connection_module

    importlib.reload(connection_module)
    connection_module.init_db()

    verify = sqlite3.connect(str(db_path))
    carbon_columns = {row[1] for row in verify.execute("PRAGMA table_info(carbon_results)")}
    usage_columns = {row[1] for row in verify.execute("PRAGMA table_info(usage_data)")}
    tables = {row[0] for row in verify.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    preserved_row = verify.execute(
        "SELECT id, energy_kwh, carbon_kg_co2, region FROM carbon_results WHERE id = 1"
    ).fetchone()
    verify.close()

    assert {"provider", "region_key", "data_quality"}.issubset(carbon_columns)
    assert {"provider", "region_key", "data_quality"}.issubset(usage_columns)
    assert "renewable_energy_contracts" in tables
    assert preserved_row == (1, 10.0, 2.0, "india")
