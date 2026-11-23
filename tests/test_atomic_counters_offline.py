"""Offline sequencing tests for the two-connection atomic-counter probe (#628).

These tests drive ``run_probe`` from ``tests/test_live_atomic_counters.py``
against an in-memory fake driver, plus a check that the lesson recipe really
uses the ODKU increment. They validate the SEQUENCING of the probe harness
(two connections, bounded retries, teardown-on-failure) only — they are NOT
live CUBRID evidence and no result here says anything about a real server.
The live claim is exercised by ``tests/test_live_atomic_counters.py`` with
``CUBRID_TEST_URL`` set.
"""

from __future__ import annotations

import datetime
import importlib.util
import re
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE_TEST = ROOT / "tests/test_live_atomic_counters.py"
RECIPE = ROOT / "fundamentals/pycubrid/13_atomic_counters.py"


def load_live_module(monkeypatch):
    try:
        import pycubrid  # noqa: F401
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "pycubrid", MagicMock(name="pycubrid"))
    spec = importlib.util.spec_from_file_location("live_atomic_counters", LIVE_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UnknownTableError(Exception):
    """Mimics pycubrid's table-not-found error (CAS errno -493, SQLSTATE S0002)."""

    errno = -493
    sqlstate = "S0002"


class FakeCubrid:
    """In-memory stand-in for the counter table; increments are atomic per call."""

    def __init__(self):
        self.lock = threading.Lock()
        self.rows: dict[tuple[str, datetime.date], int] = {}
        self.tables: set[str] = set()
        self.fail_next_increments = 0

    def connect(self):
        return FakeConnection(self)


class FakeCursor:
    def __init__(self, state: FakeCubrid, pending: dict):
        self.state = state
        self.pending = pending

    def execute(self, sql, params=None):
        flat = " ".join(str(sql).split()).upper()
        name = re.search(r"INTO\s+(\w+)|EXISTS\s+(\w+)|FROM\s+(\w+)", flat)
        table = (name.group(1) or name.group(2) or name.group(3)) if name else None
        if flat.startswith("DROP TABLE"):
            self.state.tables.discard(table)
        elif flat.startswith("CREATE TABLE"):
            self.state.tables.add(table)
        elif flat.startswith("INSERT INTO") and "ON DUPLICATE KEY UPDATE" in flat:
            with self.state.lock:  # one statement = one atomic increment
                if self.state.fail_next_increments > 0:
                    self.state.fail_next_increments -= 1
                    raise RuntimeError("-631: lock timeout")
                key, day = params[0], params[1]
                # Buffer the increment; it only becomes visible on commit,
                # so a failed transaction rolls back like a real one.
                base = self.pending.get((key, day), self.state.rows.get((key, day), 0))
                self.pending[(key, day)] = base + params[3]
        elif flat.startswith("INSERT INTO"):
            key, day = params[0], params[1]
            self.pending[(key, day)] = 0  # seed row: hit_count literal 0 in the SQL
        elif flat.startswith("SELECT 1 FROM"):
            # Existence probe: only the unknown-table error (-493 / S0002) means absent.
            if table.upper() not in {t.upper() for t in self.state.tables}:
                raise UnknownTableError(f"-493: unknown table {table}")
        elif flat.startswith("SELECT HIT_COUNT"):
            self._row = (
                (
                    self.state.rows.get(
                        (params[0], params[1]),
                    ),
                ),
            )  # fetchone -> (count,)
        elif flat.startswith("SELECT COUNT(*)"):
            self._row = (1 if table.upper() in {t.upper() for t in self.state.tables} else 0,)
        else:
            raise AssertionError(f"unexpected SQL: {flat}")

    def fetchone(self):
        return self._row[0] if self._row else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, state: FakeCubrid):
        self.state = state
        self.pending: dict[tuple[str, datetime.date], int] = {}

    def cursor(self):
        return FakeCursor(self.state, self.pending)

    def commit(self):
        with self.state.lock:
            for k, v in self.pending.items():
                self.state.rows[k] = (
                    self.state.rows.get(k, 0) + (v if k in self.pending else 0) if False else v
                )
            # seed rows overwrite, increments add — pending already holds absolute values
            for k, v in self.pending.items():
                self.state.rows[k] = v
        self.pending.clear()

    def rollback(self):
        self.pending.clear()

    def close(self):
        if self.pending:
            self.pending.clear()  # uncommitted work is discarded


@pytest.fixture
def live(monkeypatch):
    return load_live_module(monkeypatch)


def test_probe_final_count_is_the_sum_of_both_connections(live):
    state = FakeCubrid()
    key = "probe-offline"
    day = datetime.date(2026, 11, 22)
    report = live.run_probe(state.connect, key, day, per_connection=50)
    assert report["final"] == 100 == report["expected"]
    assert report["attempts"] == 1
    assert report["errors"] == []
    assert live.PROBE_TABLE not in state.tables  # torn down


def test_probe_retries_boundedly_on_lock_timeout(live):
    state = FakeCubrid()
    state.fail_next_increments = 1  # first increment of the first attempt times out
    report = live.run_probe(
        state.connect, "probe-retry", datetime.date(2026, 11, 22), per_connection=10
    )
    assert report["attempts"] == 2  # one retry, then success; never unbounded
    # No increment is lost: attempt 1's surviving connection committed 10, the
    # retried attempt adds 2 x 10 on top — final is every successful increment.
    assert report["final"] == 30


def test_probe_tears_down_even_when_every_attempt_fails(live):
    state = FakeCubrid()
    state.fail_next_increments = 10_000  # every increment "times out"
    with pytest.raises(RuntimeError, match="lock timeout"):
        live.run_probe(
            state.connect,
            "probe-fail",
            datetime.date(2026, 11, 22),
            per_connection=5,
            max_attempts=2,
        )
    assert live.PROBE_TABLE not in state.tables  # finally-drop still ran


def test_probe_refuses_and_preserves_a_preexisting_probe_table(live):
    """Ownership guard: when the fixed-name probe table already exists, the
    probe refuses to run and must not delete that foreign table on failure."""
    state = FakeCubrid()
    state.tables.add(live.PROBE_TABLE)  # foreign table already present
    with pytest.raises(RuntimeError, match="already exists"):
        live.run_probe(state.connect, "probe-guard", datetime.date(2026, 11, 22), per_connection=1)
    assert live.PROBE_TABLE in state.tables  # survived the refused run


def test_recipe_uses_on_duplicate_key_update_increment(monkeypatch):
    try:
        import pycubrid  # noqa: F401
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "pycubrid", MagicMock(name="pycubrid"))
    spec = importlib.util.spec_from_file_location("atomic_counters_recipe", RECIPE)
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    cursor = MagicMock()
    recipe.record_event(cursor, "k", datetime.date(2026, 11, 22), 3)
    sql = " ".join(str(cursor.execute.call_args.args[0]).split())
    assert "ON DUPLICATE KEY UPDATE" in sql.upper()
    assert "hit_count = hit_count + ?" in sql
    assert cursor.execute.call_args.args[1] == ("k", datetime.date(2026, 11, 22), 3, 3)
