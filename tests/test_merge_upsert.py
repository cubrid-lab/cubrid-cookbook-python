"""Offline ownership and failure checks for the MERGE lesson's entry point."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "fundamentals/pycubrid/07_merge_upsert.py"
TARGET = "cookbook_merge_products"
STAGE = "cookbook_product_stage"
UNRELATED = "cookbook_unrelated"
SENTINEL = [("keep", "existing synthetic row", 123)]
FIRST = [
    ("SKU-100", "Keyboard", 4999, 1),
    ("SKU-200", "Mouse", 2599, 1),
    ("SKU-300", "Monitor", 19999, 1),
]
SECOND = [
    ("SKU-100", "Keyboard Pro", 6999, 1),
    ("SKU-200", "Mouse", 2599, 0),
    ("SKU-300", "Monitor", 18999, 1),
    ("SKU-400", "Dock", 7999, 1),
]


class DatabaseError(Exception):
    pass


class Connection:
    """Small SQL fake: records state changes without claiming server validation."""

    def __init__(self, existing=()):
        self.tables = {name: deepcopy(SENTINEL) for name in (UNRELATED, *existing)}
        self.calls = []
        self.snapshots = []
        self.cursors = []
        self.created = set()
        self.commits = 0
        self.closed = 0
        self.failures = {}
        self.collision = DatabaseError("table already exists")

    def fail(self, operation):
        if operation in self.failures:
            raise self.failures[operation]

    def cursor(self):
        self.fail(f"cursor:{len(self.cursors) + 1}")
        cursor = Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1
        self.fail(f"commit:{self.commits}")

    def close(self):
        self.closed += 1
        self.fail("connection.close")


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self.rows = []
        self.closed = 0

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        conn = self.conn
        conn.calls.append((sql, params))
        if sql.startswith("CREATE TABLE "):
            table = sql.split()[2]
            conn.fail(f"create:{table}")
            if table in conn.tables:
                raise conn.collision
            conn.tables[table] = []
            conn.created.add(table)
        elif sql.startswith("DROP TABLE "):
            table = sql.split()[-1]
            # Inject a cleanup failure after a successful CREATE, so the old
            # setup's unconditional DROP does not prevent the main-path case.
            if table in conn.created:
                conn.fail(f"drop:{table}")
            conn.tables.pop(table, None)
        elif sql == f"DELETE FROM {STAGE}":
            conn.tables[STAGE].clear()
        elif sql.startswith(f"MERGE INTO {TARGET} "):
            conn.fail("merge")
            assert sql.count("?") == 2
            assert params is not None and len(params) == 2 and params[0] == params[1]
            products = {row[0]: row for row in conn.tables[TARGET]}
            for row in conn.tables[STAGE]:
                products[row[0]] = (*row, 1, params[0])
            conn.tables[TARGET] = list(products.values())
        elif sql.startswith(f"UPDATE {TARGET} "):
            assert f"FROM {STAGE} s WHERE s.sku = p.sku" in sql
            present = {row[0] for row in conn.tables[STAGE]}
            self.rowcount = sum(row[0] not in present for row in conn.tables[TARGET])
            conn.tables[TARGET] = [
                (*row[:3], 0, row[4]) if row[0] not in present else row
                for row in conn.tables[TARGET]
            ]
        else:
            assert sql == (
                f"SELECT sku, name, price_cents, active, last_seen_utc FROM {TARGET} ORDER BY sku"
            )
            self.rows = sorted(conn.tables[TARGET])

    def executemany(self, sql, rows):
        assert sql == f"INSERT INTO {STAGE} (sku, name, price_cents) VALUES (?, ?, ?)"
        rows = list(rows)
        self.conn.calls.append((sql, rows))
        self.conn.tables[STAGE].extend(rows)

    def fetchall(self):
        self.conn.snapshots.append(deepcopy(self.rows))
        return self.rows

    def close(self):
        self.closed += 1
        self.conn.fail(f"cursor.close:{self.conn.cursors.index(self) + 1}")
        if len(self.conn.snapshots) == 2:
            self.conn.fail("cursor.close:after_snapshots")


def run_recipe(conn):
    driver = SimpleNamespace(DatabaseError=DatabaseError, connect=mock.Mock(return_value=conn))
    with mock.patch.dict(sys.modules, {"pycubrid": driver}):
        runpy.run_path(str(RECIPE), run_name="__main__")
    driver.connect.assert_called_once()


def dropped(conn):
    return [sql.split()[-1] for sql, _ in conn.calls if sql.startswith("DROP TABLE ")]


@pytest.mark.parametrize("existing", [(TARGET,), (STAGE,), (TARGET, STAGE)])
def test_existing_rows_survive_without_running_a_snapshot(existing, capsys):
    conn = Connection(existing)
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is conn.collision
    assert conn.tables == {name: SENTINEL for name in (UNRELATED, *existing)}
    assert not set(existing).intersection(dropped(conn))
    assert conn.snapshots == []
    assert "Loaded snapshot" not in capsys.readouterr().out
    assert conn.closed == 1


@pytest.mark.parametrize("table,owned", [(TARGET, []), (STAGE, [TARGET])])
def test_create_failure_cleans_up_only_successfully_created_tables(table, owned):
    conn = Connection()
    original = DatabaseError("CREATE failed")
    conn.failures[f"create:{table}"] = original
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert dropped(conn) == owned
    assert conn.tables == {UNRELATED: SENTINEL}
    assert conn.closed == 1


@pytest.mark.parametrize("failure", ["commit:1", "merge"])
def test_failure_after_create_cleans_up_both_owned_tables(failure):
    conn = Connection()
    original = DatabaseError("lesson failed")
    conn.failures[failure] = original
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert sorted(dropped(conn)) == sorted([STAGE, TARGET])
    assert conn.tables == {UNRELATED: SENTINEL}
    assert conn.closed == 1


def test_both_snapshots_bound_values_and_golden_output_are_preserved(capsys):
    conn = Connection()
    run_recipe(conn)

    assert [[row[:4] for row in snapshot] for snapshot in conn.snapshots] == [FIRST, SECOND]
    # Missing SKU-200 keeps the timestamp from its first appearance.
    assert conn.snapshots[0][1][4] == conn.snapshots[1][1][4]
    assert conn.tables == {UNRELATED: SENTINEL}
    assert conn.closed == 1
    assert all(cursor.closed == 1 for cursor in conn.cursors)
    inserts = [(sql, params) for sql, params in conn.calls if sql.startswith("INSERT INTO ")]
    assert [rows for _, rows in inserts] == [
        [row[:3] for row in FIRST],
        [row[:3] for row in SECOND if row[3]],
    ]
    assert sum(sql.startswith("MERGE INTO ") for sql, _ in conn.calls) == 2
    output = subprocess.run(
        ["bash", str(ROOT / "scripts/normalize_output.sh")],
        input=capsys.readouterr().out,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert output == (RECIPE.parent / "expected/07_merge_upsert.expected").read_text()


@pytest.mark.parametrize("table", [STAGE, TARGET])
def test_failed_drop_is_reported_and_other_owned_table_is_still_dropped(table):
    conn = Connection()
    original = DatabaseError("DROP failed")
    conn.failures[f"drop:{table}"] = original
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert set(conn.tables) == {UNRELATED, table}
    assert conn.tables[UNRELATED] == SENTINEL
    assert conn.closed == 1


@pytest.mark.parametrize(
    "failure", ["commit:4", "cursor.close:after_snapshots", "connection.close"]
)
def test_cleanup_failure_after_success_is_reported(failure):
    conn = Connection()
    original = DatabaseError("cleanup failed")
    conn.failures[failure] = original
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert conn.tables == {UNRELATED: SENTINEL}
    assert conn.closed == 1


@pytest.mark.parametrize("failure", [f"create:{TARGET}", f"create:{STAGE}", "merge"])
def test_original_failure_survives_cleanup_and_connection_errors(failure):
    conn = Connection()
    original = DatabaseError("original lesson failure")
    conn.failures.update(
        {
            failure: original,
            f"drop:{STAGE}": DatabaseError("stage cleanup failed"),
            f"drop:{TARGET}": DatabaseError("target cleanup failed"),
            "cursor.close:1": DatabaseError("cursor cleanup failed"),
            "connection.close": DatabaseError("connection cleanup failed"),
        }
    )
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert conn.tables[UNRELATED] == SENTINEL
    assert conn.closed == 1


def test_cursor_creation_failure_still_closes_connection_without_dropping_tables():
    conn = Connection((TARGET, STAGE))
    original = DatabaseError("cursor failed")
    conn.failures["cursor:1"] = original
    conn.failures["connection.close"] = DatabaseError("connection cleanup failed")
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is original
    assert conn.tables == {name: SENTINEL for name in (UNRELATED, TARGET, STAGE)}
    assert conn.calls == []
    assert conn.closed == 1


def test_setup_error_survives_cursor_close_failure():
    conn = Connection((STAGE,))
    conn.failures["cursor.close:1"] = DatabaseError("cursor cleanup failed")
    with pytest.raises(DatabaseError) as caught:
        run_recipe(conn)

    assert caught.value is conn.collision
    assert conn.tables == {UNRELATED: SENTINEL, STAGE: SENTINEL}
    assert conn.closed == 1
