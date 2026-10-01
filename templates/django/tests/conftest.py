"""Isolate the Django/SQLAlchemy bridge against a configured live CUBRID DB."""

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
def django_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, ModuleType]]:
    url = os.environ.get("CUBRID_TEST_URL")
    if not url:
        pytest.skip("CUBRID_TEST_URL is required for the live Django bridge test")

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    if make_url(url).drivername != "cubrid+pycubrid":
        pytest.fail("Django bridge live tests require a cubrid+pycubrid CUBRID URL", pytrace=False)

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "settings")
    import django

    django.setup()
    db = import_module("app.db")
    engine = create_engine(url)
    try:
        # An explicitly configured but unreachable database must fail.
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1

        existing = {name.casefold() for name in inspect(engine).get_table_names()}
        if "cookbook_items" in existing:
            pytest.fail(
                "Django bridge live test requires a dedicated database without cookbook_items",
                pytrace=False,
            )

        monkeypatch.setattr(db, "engine", engine)
        monkeypatch.setattr(
            db,
            "SessionLocal",
            sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True),
        )
        views = import_module("app.views")
        monkeypatch.setattr(views, "_tables_initialized", False)
        try:
            yield db, views
        finally:
            # The first HTTP request lazily creates this one table. If setup or
            # assertions fail partway through, remove only what this run made.
            present = {name.casefold() for name in inspect(engine).get_table_names()}
            if "cookbook_items" in present:
                db.Base.metadata.drop_all(bind=engine, tables=[db.CookbookItem.__table__])
    finally:
        engine.dispose()
