"""Shared fixtures for the dashboard AppTest suite.

The suite runs against a live CUBRID instance when ``CUBRID_TEST_URL`` is set,
for example ``cubrid+pycubrid://dba@localhost:33000/testdb``. Without it, it
falls back to a SQLite file shared for the whole session: the five recipes
are standalone pages that intentionally view the same ``cookbook_`` demo
tables, exactly like a live CUBRID deployment shared by every page, so the
suite still runs without a database during local development or in offline
CI jobs.

Every recipe's ``CREATE TABLE`` statement uses the CUBRID/MySQL-style
``AUTO_INCREMENT`` keyword. SQLite accepts that token in the recipes' DDL as
part of the column type, but no longer treats the column as the special
``INTEGER PRIMARY KEY`` ROWID alias: inserting without an ID then stores NULL.
Rather than changing the recipes themselves — each is documented as a
standalone, copy-and-run single file — this module injects a SQLAlchemy
``before_cursor_execute`` hook that strips the keyword only for engines
connected to this suite's SQLite file. The recipes create their own cached
engines, so the listener must be registered on SQLAlchemy's ``Engine`` class,
but the fixture-local listener checks the target URL before changing SQL. A
live CUBRID run does not register the hook at all. The listener is removed at
the end of the session, including when schema cleanup fails.
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


def _drop_auto_increment_for_sqlite(conn, cursor, statement, parameters, context, executemany):
    """Make the recipes' CUBRID/MySQL-style DDL runnable on SQLite.

    SQLite's ``INTEGER PRIMARY KEY`` already autoincrements, but the extra
    ``AUTO_INCREMENT`` token prevents that ROWID behavior. Strip it only from
    statements sent to this suite's SQLite file. Every other dialect (including
    live CUBRID) is passed through unmodified. Registered and removed by
    ``_dashboard_schema_lifecycle``, not at import time — see the module
    docstring. The fixture-local listener filters by URL first.
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
    ``cookbook_products``) both before and after the session, so an interrupted
    run in this suite's dedicated live CUBRID database, or its offline SQLite
    file, does not affect a later dashboard run. Also registers and removes a
    target-URL-scoped SQLite ``AUTO_INCREMENT`` hook (see the module docstring)
    only while this session's tests run.
    """
    engine = create_engine(dashboard_database_url)

    def _drop_all() -> None:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS cookbook_sales"))
            connection.execute(text("DROP TABLE IF EXISTS cookbook_products"))

    listener = None
    if engine.dialect.name == "sqlite":

        def listener(conn, cursor, statement, parameters, context, executemany):
            if conn.engine.url != engine.url:
                return statement, parameters
            return _drop_auto_increment_for_sqlite(
                conn, cursor, statement, parameters, context, executemany
            )

        event.listen(Engine, "before_cursor_execute", listener, retval=True)
    try:
        _drop_all()
        yield
    finally:
        try:
            _drop_all()
        finally:
            try:
                engine.dispose()
            finally:
                if listener is not None:
                    event.remove(Engine, "before_cursor_execute", listener)
