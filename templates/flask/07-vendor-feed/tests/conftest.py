"""Database fixtures for this recipe's test suite.

The suite runs against a live CUBRID instance when ``CUBRID_TEST_URL`` is set,
for example ``cubrid+pycubrid://dba@localhost:33000/testdb``. Without it, each
test falls back to its own SQLite file so the suite still runs during local
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
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

# Make the recipe modules (app, database, models) importable no matter which
# directory pytest is started from.
RECIPE_ROOT = Path(__file__).resolve().parents[1]
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")

# create_app() falls back to DATABASE_URL when no database URI is passed in.
# Point it at the test database so the suite can never reach a real one.
os.environ["DATABASE_URL"] = CUBRID_TEST_URL or "sqlite://"


def pytest_report_header() -> str:
    if CUBRID_TEST_URL:
        shown = make_url(CUBRID_TEST_URL).render_as_string(hide_password=True)
        return f"database: live CUBRID ({shown})"
    return "database: per-test SQLite file fallback (set CUBRID_TEST_URL to test against CUBRID)"


@pytest.fixture()
def database_config(tmp_path: Path) -> Iterator[dict[str, object]]:
    """Yield Flask-SQLAlchemy settings for the test database, starting from empty tables."""
    importlib.import_module("models")  # registers the recipe's tables on db.metadata
    metadata = importlib.import_module("database").db.metadata

    url = CUBRID_TEST_URL or f"sqlite:///{tmp_path / 'test.db'}"
    # Every test builds its own app, and with it its own engine. NullPool closes
    # each connection as soon as it is released, so idle connections cannot
    # pile up on the CUBRID broker over the course of the suite.
    cleanup_engine = create_engine(url, poolclass=NullPool)
    try:
        # A live database outlives the test run, so clear out tables left behind
        # by an interrupted run before the app creates fresh ones.
        metadata.drop_all(bind=cleanup_engine)
        yield {
            "SQLALCHEMY_DATABASE_URI": url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
        }
    finally:
        metadata.drop_all(bind=cleanup_engine)
        cleanup_engine.dispose()
