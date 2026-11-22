"""Offline resource-ownership checks for the pool/retry teaching recipe."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path
from unittest import mock

import pytest

RECIPE = Path(__file__).resolve().parents[1] / "fundamentals/pycubrid/12_pool_retry_worker.py"


class OperationalError(Exception):
    pass


class InterfaceError(Exception):
    pass


class FakeCursor:
    def __init__(self, error=None, stage="execute", close_error=None):
        self.error = error
        self.stage = stage
        self.close_error = close_error
        self.close_calls = 0
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)
        if self.stage == "execute" and self.error is not None:
            raise self.error

    def fetchone(self):
        if self.stage == "fetch" and self.error is not None:
            raise self.error
        return (1,)

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class FakeConnection:
    def __init__(self, cursor=None, cursor_error=None, close_error=None):
        self.probe = cursor or FakeCursor()
        self.cursor_error = cursor_error
        self.close_error = close_error
        self.close_calls = 0

    def cursor(self):
        if self.cursor_error is not None:
            raise self.cursor_error
        return self.probe

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


@pytest.fixture
def recipe():
    driver = types.ModuleType("pycubrid")
    driver.OperationalError = OperationalError
    driver.InterfaceError = InterfaceError
    driver.connect = mock.Mock()
    spec = importlib.util.spec_from_file_location("pool_retry_recipe", RECIPE)
    module = importlib.util.module_from_spec(spec)
    # Load the actual recipe while replacing only the driver boundary.
    with mock.patch.dict("sys.modules", {"pycubrid": driver}):
        spec.loader.exec_module(module)
    module.driver = driver
    with mock.patch.object(module.time, "sleep") as sleep:
        module.sleep = sleep
        yield module


def test_health_check_keeps_healthy_connection_and_closes_cursor(recipe, capsys):
    connection = FakeConnection()
    recipe.driver.connect.return_value = connection
    pool = recipe.ConnectionPool(size=1)
    pool.health_check()
    assert pool.get() is connection
    assert connection.probe.statements == ["SELECT 1"]
    assert connection.probe.close_calls == 1
    assert connection.close_calls == 0
    assert recipe.driver.connect.call_count == 1
    assert "healthy=1, replaced=0" in capsys.readouterr().out


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
@pytest.mark.parametrize("stage", ["cursor", "execute", "fetch"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_health_check_closes_owned_resources(
    recipe, error_type, stage, cleanup_fails, capsys
):
    failure = error_type("probe failed")
    close_error = ValueError("cleanup failed") if cleanup_fails else None
    cursor = FakeCursor(error=failure, stage=stage, close_error=close_error)
    bad = FakeConnection(
        cursor=cursor,
        cursor_error=failure if stage == "cursor" else None,
        close_error=close_error,
    )
    replacement = FakeConnection()
    recipe.driver.connect.side_effect = [bad, replacement]
    pool = recipe.ConnectionPool(size=1)
    pool.health_check()
    assert pool.get() is replacement
    assert cursor.close_calls == (0 if stage == "cursor" else 1)
    assert bad.close_calls == 1
    assert replacement.close_calls == 0
    assert recipe.driver.connect.call_count == 2
    assert "healthy=0, replaced=1" in capsys.readouterr().out


def test_health_replacement_failure_does_not_retain_closed_connection(recipe):
    bad = FakeConnection(cursor=FakeCursor(error=OperationalError("probe failed")))
    other = FakeConnection()
    failure = OperationalError("replacement unavailable")
    recipe.driver.connect.side_effect = [bad, other, failure]
    pool = recipe.ConnectionPool(size=2)
    with pytest.raises(OperationalError) as caught:
        pool.health_check()
    assert caught.value is failure
    assert bad.probe.close_calls == 1
    assert bad.close_calls == 1
    assert pool._connections == [other]


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_healthy_probe_with_cursor_close_error_still_replaces_connection(recipe, error_type):
    bad = FakeConnection(cursor=FakeCursor(close_error=error_type("close failed")))
    replacement = FakeConnection()
    recipe.driver.connect.side_effect = [bad, replacement]
    pool = recipe.ConnectionPool(size=1)
    pool.health_check()
    assert pool.get() is replacement
    assert bad.probe.close_calls == 1
    assert bad.close_calls == 1


def test_health_check_replaces_multiple_failures_without_skipping_neighbors(recipe, capsys):
    first = FakeConnection(cursor=FakeCursor(error=OperationalError("first")))
    healthy = FakeConnection()
    last = FakeConnection(cursor=FakeCursor(error=InterfaceError("last")))
    replacements = [FakeConnection(), FakeConnection()]
    recipe.driver.connect.side_effect = [first, healthy, last, *replacements]
    pool = recipe.ConnectionPool(size=3)
    pool.health_check()
    assert pool._connections == [replacements[0], healthy, replacements[1]]
    assert [conn.close_calls for conn in [first, healthy, last]] == [1, 0, 1]
    assert all(conn.probe.close_calls == 1 for conn in [first, healthy, last])
    assert "healthy=1, replaced=2" in capsys.readouterr().out


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_nonretryable_probe_error_keeps_original_exception(recipe, cleanup_fails):
    failure = ValueError("probe failed")
    cursor = FakeCursor(
        error=failure, close_error=InterfaceError("close failed") if cleanup_fails else None
    )
    connection = FakeConnection(cursor=cursor)
    recipe.driver.connect.return_value = connection
    pool = recipe.ConnectionPool(size=1)
    with pytest.raises(ValueError) as caught:
        pool.health_check()
    assert caught.value is failure
    assert cursor.close_calls == 1
    assert recipe.driver.connect.call_count == 1


def test_successful_callback_returns_connection_without_closing(recipe):
    connection = FakeConnection()
    recipe.driver.connect.return_value = connection
    pool = recipe.ConnectionPool(size=1)
    callback = mock.Mock(return_value="done")
    assert recipe.run_with_retry(pool, callback) == "done"
    callback.assert_called_once_with(connection)
    assert pool.get() is connection
    assert connection.close_calls == 0
    recipe.sleep.assert_not_called()


def test_retryable_callback_errors_keep_backoff_and_replace_connections(recipe):
    connections = [FakeConnection() for _ in range(3)]
    recipe.driver.connect.side_effect = connections
    pool = recipe.ConnectionPool(size=1)
    callback = mock.Mock(side_effect=[OperationalError("first"), InterfaceError("second"), "done"])
    assert recipe.run_with_retry(pool, callback, max_retries=3) == "done"
    assert callback.call_args_list == [mock.call(conn) for conn in connections]
    assert [conn.close_calls for conn in connections] == [1, 1, 0]
    assert pool.get() is connections[-1]
    assert recipe.sleep.call_args_list == [mock.call(0.1), mock.call(0.2)]


@pytest.mark.parametrize("max_retries", [0, 2])
def test_retry_exhaustion_closes_last_connection_and_preserves_error(recipe, max_retries):
    connections = [
        FakeConnection(close_error=ValueError("close failed")) for _ in range(max_retries + 1)
    ]
    recipe.driver.connect.side_effect = connections
    pool = recipe.ConnectionPool(size=1)
    failure = OperationalError("operation failed")
    callback = mock.Mock(side_effect=failure)
    with pytest.raises(OperationalError) as caught:
        recipe.run_with_retry(pool, callback, max_retries=max_retries)
    assert caught.value is failure
    assert callback.call_count == max_retries + 1
    assert recipe.driver.connect.call_count == max_retries + 1
    assert all(conn.close_calls == 1 for conn in connections)
    assert pool._connections == []
    assert recipe.sleep.call_args_list == [mock.call(0.1 * 2**i) for i in range(max_retries)]


@pytest.mark.parametrize("failure", [ValueError("callback failed"), KeyboardInterrupt()])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_nonretryable_callback_closes_connection_and_preserves_error(
    recipe, failure, cleanup_fails
):
    bad = FakeConnection(close_error=ValueError("close failed") if cleanup_fails else None)
    replacement = FakeConnection()
    recipe.driver.connect.side_effect = [bad, replacement]
    pool = recipe.ConnectionPool(size=1)
    callback = mock.Mock(side_effect=failure)
    with pytest.raises(type(failure)) as caught:
        recipe.run_with_retry(pool, callback)
    assert caught.value is failure
    callback.assert_called_once_with(bad)
    assert bad.close_calls == 1
    assert recipe.driver.connect.call_count == 1
    recipe.sleep.assert_not_called()
    assert pool.get() is replacement
