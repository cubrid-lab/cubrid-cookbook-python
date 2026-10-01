"""Failure-path coverage for the dashboard suite's session resources."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

import conftest


class _FakeConnection:
    def execute(self, _statement: object) -> None:
        pass


class _FakeContext(AbstractContextManager[_FakeConnection]):
    def __init__(self, *, fail: bool) -> None:
        self.fail = fail

    def __enter__(self) -> _FakeConnection:
        if self.fail:
            raise RuntimeError("simulated teardown database failure")
        return _FakeConnection()

    def __exit__(self, *_args: object) -> None:
        pass


class _FakeEngine:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.begin_calls = 0
        self.disposed = False
        self.dialect = SimpleNamespace(name="sqlite")
        self.url = make_url("sqlite:///unused.db")

    def begin(self) -> _FakeContext:
        self.begin_calls += 1
        return _FakeContext(fail=self.begin_calls == 2 and self.failure == "drop")

    def dispose(self) -> None:
        self.disposed = True
        if self.failure == "dispose":
            raise RuntimeError("simulated engine disposal failure")


@pytest.mark.parametrize("failure", ["drop", "dispose"])
def test_schema_teardown_failure_still_removes_global_hook(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    engine = _FakeEngine(failure)
    hook_events: list[str] = []
    monkeypatch.setattr(conftest, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        conftest.event, "listen", lambda *_args, **_kwargs: hook_events.append("listen")
    )
    monkeypatch.setattr(
        conftest.event, "remove", lambda *_args, **_kwargs: hook_events.append("remove")
    )

    lifecycle = conftest._dashboard_schema_lifecycle.__wrapped__("sqlite:///unused.db")
    next(lifecycle)

    with pytest.raises(
        RuntimeError, match=f"simulated .*{'database' if failure == 'drop' else 'disposal'} failure"
    ):
        next(lifecycle)

    assert hook_events == ["listen", "remove"]
    assert engine.disposed


def test_sqlite_hook_does_not_change_an_unrelated_engine(tmp_path) -> None:
    lifecycle = conftest._dashboard_schema_lifecycle.__wrapped__(
        f"sqlite:///{tmp_path / 'dashboard.db'}"
    )
    other_engine = create_engine("sqlite:///:memory:")
    try:
        next(lifecycle)
        with other_engine.begin() as connection:
            with pytest.raises(OperationalError, match="AUTO_INCREMENT"):
                connection.execute(
                    text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY AUTO_INCREMENT)")
                )
    finally:
        with pytest.raises(StopIteration):
            next(lifecycle)
        other_engine.dispose()
