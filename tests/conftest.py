"""Shared pytest fixtures.

Sets required environment variables *before* any test imports
``database.service`` (which imports ``utils.encryption``, which raises at
import time if ``ENCRYPTION_KEY`` is unset) or ``config``/``database.connection``
(which read ``DATABASE_URL``). Each test that touches the database gets its
own throwaway SQLite file via the ``temp_db`` fixture so tests never share
state or touch a real ``carbon_tracker.db``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENCRYPTION_KEY", "4P-rbUjRKWXL9dFWq_mJRVI3rE7IYEfjgZbp1JjRk_o=")  # test-only Fernet key
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the app at a fresh, throwaway SQLite file for one test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import importlib

    import database.connection as connection_module

    importlib.reload(connection_module)
    connection_module.init_db()

    import database.service as service_module

    importlib.reload(service_module)

    yield service_module
