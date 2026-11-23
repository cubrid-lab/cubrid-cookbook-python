"""Offline regression tests for the cursor memory probe's timing and cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def probe(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "fundamentals/pycubrid/15_cursor_memory_bound.py"
    spec = importlib.util.spec_from_file_location("cursor_memory_recipe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchmany.side_effect = [[(1,), (2,)], [(3,)], []]
    cursor.fetchall.return_value = [(1,), (2,), (3,)]
    monkeypatch.setattr(module, "ROW_COUNT", 3)
    monkeypatch.setattr(module, "get_connection", MagicMock(return_value=conn))
    # A deterministic monotonic clock verifies elapsed time without sleeping.
    monkeypatch.setattr(
        module, "perf_counter", MagicMock(side_effect=[10.0, 10.375]), raising=False
    )
    monkeypatch.setattr(module.tracemalloc, "start", MagicMock())
    monkeypatch.setattr(module.tracemalloc, "stop", MagicMock())
    monkeypatch.setattr(
        module.tracemalloc, "get_traced_memory", MagicMock(return_value=(512, 4096))
    )
    return module, conn, cursor


@pytest.mark.parametrize("keep_rows", [False, True])
def test_scan_reports_memory_and_real_elapsed_time(probe, keep_rows):
    module, conn, cursor = probe

    assert module.measure_peak_memory(100, keep_rows=keep_rows) == (4096, 0.375)

    module.get_connection.assert_called_once_with(100)
    cursor.execute.assert_called_once_with(
        "SELECT id, payload, created_at FROM cookbook_fetch_probe"
    )
    if keep_rows:
        cursor.fetchall.assert_called_once_with()
        cursor.fetchmany.assert_not_called()
    else:
        assert cursor.fetchmany.call_count == 3
        assert all(call.args == (10,) for call in cursor.fetchmany.call_args_list)
        cursor.fetchall.assert_not_called()
    module.tracemalloc.stop.assert_called_once_with()
    cursor.close.assert_called_once_with()
    conn.close.assert_called_once_with()


@pytest.mark.parametrize("keep_rows", [False, True])
def test_incomplete_scan_is_rejected_after_cleanup(probe, keep_rows):
    module, conn, cursor = probe
    cursor.fetchmany.side_effect = [[(1,), (2,)], []]
    cursor.fetchall.return_value = [(1,), (2,)]

    with pytest.raises(RuntimeError, match="expected 3 rows, got 2"):
        module.measure_peak_memory(100, keep_rows=keep_rows)

    module.tracemalloc.stop.assert_called_once_with()
    cursor.close.assert_called_once_with()
    conn.close.assert_called_once_with()


@pytest.mark.parametrize("operation", ["execute", "fetchmany", "fetchall", "memory_snapshot"])
def test_scan_error_survives_cleanup_errors(probe, operation):
    module, conn, cursor = probe
    original = module.DatabaseError("scan failed")
    target = (
        module.tracemalloc.get_traced_memory
        if operation == "memory_snapshot"
        else getattr(cursor, operation)
    )
    target.side_effect = original
    # Every cleanup must still be attempted, without hiding the scan error.
    module.tracemalloc.stop.side_effect = RuntimeError("trace cleanup failed")
    cursor.close.side_effect = RuntimeError("cursor cleanup failed")
    conn.close.side_effect = RuntimeError("connection cleanup failed")

    with pytest.raises(module.DatabaseError) as caught:
        module.measure_peak_memory(100, keep_rows=operation == "fetchall")

    assert caught.value is original
    module.tracemalloc.stop.assert_called_once_with()
    cursor.close.assert_called_once_with()
    conn.close.assert_called_once_with()


def test_cursor_creation_error_still_closes_connection(probe):
    module, conn, cursor = probe
    original = module.DatabaseError("cursor failed")
    conn.cursor.side_effect = original
    conn.close.side_effect = RuntimeError("connection cleanup failed")

    with pytest.raises(module.DatabaseError) as caught:
        module.measure_peak_memory(100)

    assert caught.value is original
    module.tracemalloc.start.assert_not_called()
    module.tracemalloc.stop.assert_not_called()
    cursor.close.assert_not_called()
    conn.close.assert_called_once_with()


@pytest.mark.parametrize("operation", ["trace", "cursor", "connection"])
def test_cleanup_error_after_success_is_reported_and_other_resources_close(probe, operation):
    module, conn, cursor = probe
    target = {
        "trace": module.tracemalloc.stop,
        "cursor": cursor.close,
        "connection": conn.close,
    }[operation]
    target.side_effect = RuntimeError("cleanup failed")

    with pytest.raises(RuntimeError, match="cleanup failed"):
        module.measure_peak_memory(100)

    module.tracemalloc.stop.assert_called_once_with()
    cursor.close.assert_called_once_with()
    conn.close.assert_called_once_with()
