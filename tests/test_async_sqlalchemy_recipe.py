"""Offline regression tests for the async SQLAlchemy lesson's ownership and cleanup."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

RECIPE = Path(__file__).resolve().parents[1] / "fundamentals/async/02_async_sqlalchemy.py"


class FakeConnection:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    async def run_sync(self, fn):
        # The recipe's sync helpers are told apart by name; ``drop_all`` is the metadata method.
        name = getattr(fn, "__name__", "")
        if name == "_create_demo_table":
            self.engine.events.append("create_all")
            if self.engine.fail_create:
                raise self.engine.create_error
            return None
        if name == "drop_all":
            self.engine.events.append("drop_all")
            if self.engine.fail_drop:
                raise RuntimeError("drop failed")
            return None
        return self.engine.table_exists


class FakeBegin:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    async def __aenter__(self) -> FakeConnection:
        return FakeConnection(self.engine)

    async def __aexit__(self, *exc_info) -> bool:
        return False


class FakeEngine:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.table_exists = False
        self.fail_create = False
        self.create_error: BaseException = RuntimeError("create failed")
        self.fail_drop = False
        self.disposed = 0

    def begin(self) -> FakeBegin:
        return FakeBegin(self)

    async def dispose(self) -> None:
        self.events.append("dispose")
        self.disposed += 1


@pytest.fixture
def recipe(monkeypatch):
    spec = importlib.util.spec_from_file_location("async_sqlalchemy_recipe", RECIPE)
    module = importlib.util.module_from_spec(spec)
    # SQLAlchemy resolves the recipe's ``Mapped[...]`` string annotations through sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    engine = FakeEngine()
    monkeypatch.setattr(module, "create_async_engine", lambda *a, **k: engine)

    async def ok_crud(_engine):
        engine.events.append("crud")

    monkeypatch.setattr(module, "_crud_demo", ok_crud)
    # The recipe asks the fake connection whether the table exists through ``run_sync``;
    # the lambda has no ``create_all`` name, so FakeConnection answers with ``table_exists``.
    return module, engine


async def test_success_creates_cruds_drops_and_disposes(recipe):
    module, engine = recipe

    await module.main()

    assert engine.events == ["create_all", "crud", "drop_all", "dispose"]


async def test_existing_table_is_never_modified_or_dropped(recipe):
    module, engine = recipe
    engine.table_exists = True

    with pytest.raises(RuntimeError, match="already exists"):
        await module.main()

    assert engine.events == ["dispose"]


async def test_failed_schema_creation_disposes_without_dropping(recipe):
    module, engine = recipe
    engine.fail_create = True

    with pytest.raises(RuntimeError, match="create failed"):
        await module.main()

    assert engine.events == ["create_all", "dispose"]


async def test_failed_demo_still_drops_and_disposes_and_keeps_the_original_error(
    recipe, monkeypatch
):
    module, engine = recipe

    async def broken_crud(_engine):
        engine.events.append("crud")
        raise ValueError("insert failed")

    monkeypatch.setattr(module, "_crud_demo", broken_crud)

    with pytest.raises(ValueError, match="insert failed"):
        await module.main()

    assert engine.events == ["create_all", "crud", "drop_all", "dispose"]


async def test_failed_drop_does_not_hide_the_original_error(recipe, monkeypatch, capsys):
    module, engine = recipe
    engine.fail_drop = True

    async def broken_crud(_engine):
        raise ValueError("commit failed")

    monkeypatch.setattr(module, "_crud_demo", broken_crud)

    with pytest.raises(ValueError, match="commit failed"):
        await module.main()

    assert engine.events[-1] == "dispose"
    assert "could not drop cookbook_async_orm_demo" in capsys.readouterr().err


async def test_failed_drop_after_a_successful_demo_is_reported(recipe):
    module, engine = recipe
    engine.fail_drop = True

    with pytest.raises(RuntimeError, match="drop failed"):
        await module.main()

    assert engine.events == ["create_all", "crud", "drop_all", "dispose"]


async def test_table_created_by_another_session_after_the_check_is_not_dropped(recipe):
    module, engine = recipe
    # The existence check saw no table, but the database refuses the creation because
    # another session created it in between.
    engine.fail_create = True
    engine.create_error = RuntimeError("table cookbook_async_orm_demo already exists")

    with pytest.raises(RuntimeError, match="already exists"):
        await module.main()

    assert engine.events == ["create_all", "dispose"]


def test_demo_table_creation_does_not_skip_an_existing_table(recipe):
    module, _engine = recipe
    calls: list[tuple[object, dict[str, object]]] = []

    class _Table:
        def create(self, bind: object, **kwargs: object) -> None:
            calls.append((bind, kwargs))

    class _Model:
        __table__ = _Table()

    module.CookbookAsyncOrmDemo = _Model
    sync_conn = object()

    module._create_demo_table(sync_conn)

    assert calls == [(sync_conn, {"checkfirst": False})]
