"""Database fixtures for this recipe's test suite.

The suite runs against a live CUBRID instance when ``CUBRID_TEST_URL`` is set,
for example ``cubrid+pycubrid://dba@localhost:33000/testdb``. Without it, the
tests fall back to an in-memory SQLite database so they still run during local
development. SQLite cannot catch CUBRID-specific SQL differences, so treat a
run against CUBRID as the one that counts.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool

# Make the recipe modules (database, main, models, ...) importable no matter
# which directory pytest is started from.
RECIPE_ROOT = Path(__file__).resolve().parents[1]
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

SQLITE_FALLBACK_URL = "sqlite+pysqlite:///:memory:"
CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")

# database.py builds a module-level engine from DATABASE_URL at import time.
# Point it at the test database so the suite can never reach a real one.
os.environ["DATABASE_URL"] = CUBRID_TEST_URL or SQLITE_FALLBACK_URL


def pytest_report_header() -> str:
    if CUBRID_TEST_URL:
        shown = make_url(CUBRID_TEST_URL).render_as_string(hide_password=True)
        return f"database: live CUBRID ({shown})"
    return "database: in-memory SQLite fallback (set CUBRID_TEST_URL to test against CUBRID)"


def _create_test_engine() -> Engine:
    if CUBRID_TEST_URL:
        return create_engine(CUBRID_TEST_URL)
    # StaticPool keeps a single connection, so every session sees the same
    # in-memory database.
    return create_engine(
        SQLITE_FALLBACK_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def engine() -> Iterator[Engine]:
    """Yield an engine for the test database with this recipe's tables created."""
    base = importlib.import_module("database").Base
    importlib.import_module("models")  # registers the recipe's tables on Base

    test_engine = _create_test_engine()
    try:
        # A live database outlives the test run, so clear out tables left behind
        # by an interrupted run before creating fresh ones.
        base.metadata.drop_all(bind=test_engine)
        base.metadata.create_all(bind=test_engine)
        yield test_engine
    finally:
        base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
