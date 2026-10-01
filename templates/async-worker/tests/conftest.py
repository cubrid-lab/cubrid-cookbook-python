"""Use a dedicated live CUBRID database for the worker's business-data tasks."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest

RECIPE_ROOT = Path(__file__).resolve().parents[1]
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))


@pytest.fixture()
def worker_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    url = os.environ.get("CUBRID_TEST_URL")
    if not url:
        pytest.skip("CUBRID_TEST_URL is required for live async-worker tests")

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    if make_url(url).drivername != "cubrid+pycubrid":
        pytest.fail("Async-worker live tests require a cubrid+pycubrid CUBRID URL", pytrace=False)

    database = import_module("database")
    models = import_module("models")
    engine = create_engine(url)
    try:
        # A configured but unavailable database must fail, never turn into a skip.
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1

        worker_tables = {table.name for table in models.Base.metadata.sorted_tables}
        existing = {name.casefold() for name in inspect(engine).get_table_names()}
        collisions = sorted(name for name in worker_tables if name.casefold() in existing)
        if collisions:
            pytest.fail(
                "Async-worker live tests require a dedicated database without existing "
                f"worker tables: {collisions}",
                pytrace=False,
            )

        monkeypatch.setattr(database, "engine", engine)
        monkeypatch.setattr(
            database,
            "SessionLocal",
            sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True),
        )
        try:
            models.Base.metadata.create_all(bind=engine)
            # Task modules capture session_scope at import time. Import only
            # after the test database has replaced the recipe's default engine.
            data_tasks = import_module("tasks.data_tasks")
            email_tasks = import_module("tasks.email_tasks")
            yield database, models, data_tasks, email_tasks
        finally:
            # create_all can fail halfway through; drop only this run's tables.
            present = {name.casefold() for name in inspect(engine).get_table_names()}
            created = [
                table
                for table in models.Base.metadata.sorted_tables
                if table.name.casefold() in present
            ]
            models.Base.metadata.drop_all(bind=engine, tables=created)
    finally:
        engine.dispose()
