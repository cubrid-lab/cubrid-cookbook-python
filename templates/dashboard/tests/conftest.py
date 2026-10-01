"""Shared fixtures for the dashboard AppTest suite.

The suite runs against a live CUBRID instance when ``CUBRID_TEST_URL`` is set,
for example ``cubrid+pycubrid://dba@localhost:33000/testdb``. Without it, it
falls back to a SQLite file shared for the whole session: the five recipes
are standalone pages that intentionally view the same ``cookbook_`` demo
tables, exactly like a live CUBRID deployment shared by every page, so the
suite still runs without a database during local development or in offline
CI jobs.

Every recipe's ``CREATE TABLE`` statement uses the CUBRID/MySQL-style
``AUTO_INCREMENT`` keyword, which SQLite rejects outright (its own
``INTEGER PRIMARY KEY`` column already autoincrements via its ROWID alias).
Rather than changing the recipes themselves — each is documented as a
standalone, copy-and-run single file — this module injects a SQLAlchemy
``before_cursor_execute`` hook that strips the keyword for SQLite
connections only. A live CUBRID run is never touched by the hook, so this is
the suite's injectable DB layer: only the connection target and dialect
change, never the recipe source.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")

_AUTO_INCREMENT_RE = re.compile(r"\bAUTO_INCREMENT\b", re.IGNORECASE)


@event.listens_for(Engine, "before_cursor_execute", retval=True)
def _drop_auto_increment_for_sqlite(conn, cursor, statement, parameters, context, executemany):
    """Make the recipes' CUBRID/MySQL-style DDL runnable on SQLite.

    SQLite's ``INTEGER PRIMARY KEY`` already autoincrements and rejects the
    ``AUTO_INCREMENT`` keyword outright, so this strips it from any
    statement sent to a SQLite connection. Every other dialect (including a
    live CUBRID run) is passed through unmodified.
    """
    if conn.engine.dialect.name == "sqlite" and _AUTO_INCREMENT_RE.search(statement):
        statement = _AUTO_INCREMENT_RE.sub("", statement)
    return statement, parameters


def pytest_report_header() -> str:
    if CUBRID_TEST_URL:
        shown = make_url(CUBRID_TEST_URL).render_as_string(hide_password=True)
        return f"database: live CUBRID ({shown})"
    return "database: shared SQLite file fallback (set CUBRID_TEST_URL to test against CUBRID)"


@pytest.fixture(scope="session")
def dashboard_database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """The URL every dashboard recipe should connect to for this test session.

    Session-scoped, not per-test: the five recipes are standalone pages that
    intentionally share one set of demo tables, the same way a live CUBRID
    deployment is shared by every page.
    """
    if CUBRID_TEST_URL:
        return CUBRID_TEST_URL
    db_path = tmp_path_factory.mktemp("dashboard") / "dashboard.db"
    return f"sqlite:///{db_path}"


@pytest.fixture(autouse=True)
def _point_recipes_at_test_database(dashboard_database_url: str) -> None:
    """Point every recipe's ``DATABASE_URL`` default at the test database.

    Each recipe reads ``os.environ.get("DATABASE_URL", ...)`` at import time,
    and ``streamlit.testing.v1.AppTest.from_file`` re-executes that top-level
    code on every run, so setting the environment variable here is enough to
    redirect each recipe without touching its source.
    """
    os.environ["DATABASE_URL"] = dashboard_database_url


@pytest.fixture(scope="session", autouse=True)
def _dashboard_schema_lifecycle(dashboard_database_url: str):
    """Start the session with a clean schema and drop it again afterward.

    Tables are dropped in FK-safe order (``cookbook_sales`` before its parent
    ``cookbook_products``) both before and after the session, so an
    interrupted previous run or a shared live CUBRID database is left clean
    for the suite and for whatever runs against the same database next.
    """
    engine = create_engine(dashboard_database_url)

    def _drop_all() -> None:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS cookbook_sales"))
            connection.execute(text("DROP TABLE IF EXISTS cookbook_products"))

    try:
        _drop_all()
        yield
    finally:
        _drop_all()
        engine.dispose()
