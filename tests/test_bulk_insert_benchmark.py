"""Offline ownership checks for the bulk-insert benchmark's fixed-name table."""

from __future__ import annotations

import importlib.util
from itertools import count
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
TABLE = "cookbook_bulk_test"


class DatabaseError(Exception):
    pass


class Connection:
    def __init__(self, *, existing: bool = False) -> None:
        self.tables = {"cookbook_unrelated": [(1, "keep me")]}
        if existing:
            self.tables[TABLE] = [(7, "previous data")]
        self.calls = []
        self.counts = []
        self.commits = 0
        self.closed = 0
        self.fail_prefix = None
        self.fail_commit = None
        self.fail_cursor = False
        self.fail_fetch = False
        self.error = DatabaseError("injected database failure")

    def cursor(self):
        if self.fail_cursor:
            raise self.error
        return self

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.calls.append((sql, params))
        if self.fail_prefix and sql.startswith(self.fail_prefix):
            raise self.error
        if sql.startswith("CREATE TABLE"):
            if TABLE in self.tables:
                raise self.error
            self.tables[TABLE] = []
        elif sql.startswith("DROP TABLE"):
            self.tables.pop(TABLE, None)
        elif sql.startswith("DELETE FROM"):
            self.tables[TABLE].clear()
        elif sql.startswith("INSERT INTO"):
            self.tables[TABLE].append(params)
        else:
            assert sql == f"SELECT COUNT(*) FROM {TABLE}"

    def fetchone(self):
        if self.fail_fetch:
            raise self.error
        rows = len(self.tables[TABLE])
        self.counts.append(rows)
        return (rows,)

    def commit(self):
        self.commits += 1
        if self.commits == self.fail_commit:
            raise self.error

    def close(self):
        self.closed += 1


@pytest.fixture
def benchmark(monkeypatch):
    driver = SimpleNamespace(DatabaseError=DatabaseError, connect=mock.Mock())
    spec = importlib.util.spec_from_file_location(
        "bulk_insert_benchmark", ROOT / "performance/bulk-insert/benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"pycubrid": driver}):
        spec.loader.exec_module(module)
    # Timers advance deterministically; no database timing claim is made here.
    ticks = count()
    monkeypatch.setattr(module.time, "time", lambda: next(ticks))
    return module, driver


def test_existing_table_is_not_modified(benchmark, capsys):
    module, driver = benchmark
    conn = Connection(existing=True)
    driver.connect.return_value = conn
    with pytest.raises(RuntimeError, match="fresh disposable database") as error:
        module.main()
    assert error.value.__cause__ is conn.error
    assert conn.tables[TABLE] == [(7, "previous data")]
    assert conn.tables["cookbook_unrelated"] == [(1, "keep me")]
    assert len(conn.calls) == 1
    assert conn.calls[0][0].startswith(f"CREATE TABLE {TABLE}")
    assert conn.commits == 0
    assert conn.closed == 1
    assert "Strategy" not in capsys.readouterr().out


def test_create_failure_does_not_drop_a_table(benchmark):
    module, driver = benchmark
    conn = Connection()
    conn.fail_prefix = "CREATE TABLE"
    driver.connect.return_value = conn
    with pytest.raises(RuntimeError, match="will not replace") as error:
        module.main()
    assert error.value.__cause__ is conn.error
    assert len(conn.calls) == 1
    assert TABLE not in conn.tables
    assert conn.tables["cookbook_unrelated"] == [(1, "keep me")]
    assert conn.commits == 0
    assert conn.closed == 1


def test_all_three_workloads_and_row_checks_are_preserved(benchmark, capsys):
    module, driver = benchmark
    conn = Connection()
    driver.connect.return_value = conn
    module.main()
    assert conn.counts == [500, 5000, 5000]
    assert conn.calls[0][0].startswith(f"CREATE TABLE {TABLE}")
    assert conn.calls[-1] == (f"DROP TABLE IF EXISTS {TABLE}", None)
    assert sum(sql.startswith("DROP TABLE") for sql, _ in conn.calls) == 1
    inserts = [(sql, params) for sql, params in conn.calls if sql.startswith("INSERT INTO")]
    assert len(inserts) == 10500
    assert {sql for sql, _ in inserts} == {
        f"INSERT INTO {TABLE} (name, val, is_active) VALUES (?, ?, ?)"
    }
    assert inserts[0][1] == ("row_0", 0, 1)
    assert inserts[-1][1] == ("row_4999", 4999, 1)
    assert conn.commits == 517  # setup, deletes, all strategy commits, cleanup
    assert conn.closed == 1
    assert conn.tables == {"cookbook_unrelated": [(1, "keep me")]}
    output = capsys.readouterr().out
    for number, rows in ((1, 500), (2, 5000), (3, 5000)):
        line = next(line for line in output.splitlines() if line.startswith(f"Strategy {number}"))
        assert f"{rows} rows" in line


@pytest.mark.parametrize("failure", ["delete", "insert", "fetch", "setup_commit"])
def test_post_creation_failure_cleans_up_only_owned_table(benchmark, failure):
    module, driver = benchmark
    conn = Connection()
    if failure in ("delete", "insert"):
        conn.fail_prefix = failure.upper()
    elif failure == "fetch":
        conn.fail_fetch = True
    else:
        conn.fail_commit = 1
    driver.connect.return_value = conn
    with pytest.raises(DatabaseError) as error:
        module.main()
    assert error.value is conn.error
    assert conn.calls[0][0].startswith(f"CREATE TABLE {TABLE}")
    assert conn.calls[-1] == (f"DROP TABLE IF EXISTS {TABLE}", None)
    assert sum(sql.startswith("DROP TABLE") for sql, _ in conn.calls) == 1
    assert conn.tables == {"cookbook_unrelated": [(1, "keep me")]}
    assert conn.closed == 1


def test_cursor_creation_failure_closes_connection_without_sql(benchmark):
    module, driver = benchmark
    conn = Connection(existing=True)
    conn.fail_cursor = True
    driver.connect.return_value = conn
    with pytest.raises(DatabaseError) as error:
        module.main()
    assert error.value is conn.error
    assert conn.calls == []
    assert conn.tables[TABLE] == [(7, "previous data")]
    assert conn.closed == 1


def test_connection_failure_preserves_driver_error(benchmark):
    module, driver = benchmark
    failure = DatabaseError("connection unavailable")
    driver.connect.side_effect = failure
    with pytest.raises(DatabaseError) as error:
        module.main()
    assert error.value is failure
