"""Offline fake-driver tests for the MERGE lesson's table-ownership safety (#627).

The recipe must never drop a table it did not create: existing
``cookbook_product_stage`` / ``cookbook_merge_products`` tables (which may hold
someone else's data) make the run refuse up front, a partial CREATE failure
cleans up only what was created, and a cleanup failure never replaces the
original error. Everything here runs against a fake connection — no database,
and none of these results is live CUBRID evidence.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RECIPE = Path(__file__).resolve().parents[1] / "fundamentals/pycubrid/07_merge_upsert.py"

TARGET = "cookbook_merge_products"
STAGE = "cookbook_product_stage"


def load_module():
    spec = importlib.util.spec_from_file_location("merge_upsert_recipe", RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module(monkeypatch):
    # The recipe imports pycubrid at module level; where the driver is not
    # installed (offline sandbox) a stub keeps the import working. CI has the
    # real driver and this stub is simply unused.
    try:
        import pycubrid  # noqa: F401
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "pycubrid", MagicMock(name="pycubrid"))
    return load_module()


def table_of(sql: str) -> str | None:
    m = re.search(
        r"\b(?:FROM|DROP TABLE IF EXISTS|CREATE TABLE)\s+(\w+)",
        " ".join(str(sql).split()),
        re.IGNORECASE,
    )
    return m.group(1) if m else None


class UnknownTableError(Exception):
    """Mimics pycubrid's table-not-found error (CAS errno -493, SQLSTATE S0002)."""

    errno = -493
    sqlstate = "S0002"


def make_conn(existing=(), create_fail=(), drop_fail=(), fail_on=None, probe_error=None):
    """A fake pycubrid connection whose cursor fails where told.

    - `existing`: tables the existence probe reports as present
    - `create_fail`: table names whose CREATE TABLE raises
    - `drop_fail`: table names whose DROP TABLE raises
    - `fail_on`: substring that makes any other execute() raise (e.g. MERGE)
    - `probe_error`: exception the existence probe raises for missing tables
      (defaults to the driver's unknown-table error, -493 / S0002)
    """
    conn = MagicMock(name="conn")
    cursor = conn.cursor.return_value
    cursor.rowcount = 0
    cursor.fetchall.return_value = []

    def execute(sql, params=None):
        flat = " ".join(str(sql).split())
        name = table_of(flat)
        if flat.upper().startswith("SELECT 1 FROM"):
            if name in existing:
                return
            raise probe_error or UnknownTableError(f"-493: unknown table {name}")
        if flat.upper().startswith("CREATE TABLE") and name in create_fail:
            raise RuntimeError(f"create failed for {name}")
        if flat.upper().startswith("DROP TABLE") and name in drop_fail:
            raise RuntimeError(f"drop failed for {name}")
        if fail_on and fail_on.lower() in flat.lower():
            raise RuntimeError(f"boom on {fail_on}")

    cursor.execute.side_effect = execute
    return conn, cursor


def executed(cursor, prefix):
    return [
        " ".join(str(c.args[0]).split())
        for c in cursor.execute.call_args_list
        if " ".join(str(c.args[0]).split()).upper().startswith(prefix)
    ]


def test_setup_refuses_existing_target_table(module):
    conn, cursor = make_conn(existing={TARGET})
    with pytest.raises(RuntimeError, match="refusing to run.*cookbook_merge_products"):
        module.setup_schema(conn)
    # No destructive SQL ran at all: sentinel data in the existing table survives.
    assert executed(cursor, "DROP") == []
    assert executed(cursor, "CREATE") == []


def test_setup_refuses_existing_stage_table(module):
    conn, cursor = make_conn(existing={STAGE})
    with pytest.raises(RuntimeError, match="refusing to run"):
        module.setup_schema(conn)
    assert executed(cursor, "DROP") == []
    assert executed(cursor, "CREATE") == []


def test_setup_creates_both_and_returns_owned(module):
    conn, cursor = make_conn()
    owned = module.setup_schema(conn)
    assert owned == [TARGET, STAGE]
    creates = executed(cursor, "CREATE TABLE")
    assert len(creates) == 2
    assert TARGET in creates[0] and STAGE in creates[1]


def test_first_create_failure_drops_nothing(module):
    conn, cursor = make_conn(create_fail={TARGET})
    with pytest.raises(RuntimeError, match="create failed"):
        module.setup_schema(conn)
    assert executed(cursor, "DROP") == []


def test_second_create_failure_drops_only_target(module):
    conn, cursor = make_conn(create_fail={STAGE})
    with pytest.raises(RuntimeError, match="create failed"):
        module.setup_schema(conn)
    drops = executed(cursor, "DROP TABLE")
    assert len(drops) == 1 and TARGET in drops[0]


def test_create_failure_preserves_original_error_when_cleanup_fails(module):
    conn, cursor = make_conn(create_fail={STAGE}, drop_fail={TARGET})
    with pytest.raises(RuntimeError, match="create failed") as excinfo:
        module.setup_schema(conn)
    # The cleanup failure is the cause, not the raised error.
    assert excinfo.value.__cause__ is not None
    assert "drop failed" in str(excinfo.value.__cause__)


def test_cleanup_drops_only_owned_newest_first(module):
    conn, cursor = make_conn()
    module.cleanup(conn, [TARGET, STAGE])
    drops = executed(cursor, "DROP TABLE")
    assert [table_of(d) for d in drops] == [STAGE, TARGET]


def test_cleanup_with_empty_owned_drops_nothing(module):
    conn, cursor = make_conn()
    module.cleanup(conn, [])
    assert executed(cursor, "DROP") == []


def test_cleanup_partial_failure_still_drops_rest_and_raises(module, capsys):
    conn, cursor = make_conn(drop_fail={STAGE})
    with pytest.raises(RuntimeError, match="cleanup failed.*cookbook_product_stage"):
        module.cleanup(conn, [TARGET, STAGE])
    drops = [table_of(d) for d in executed(cursor, "DROP TABLE")]
    assert drops == [STAGE, TARGET]  # both attempted, target succeeded
    # "Cleaned up" is claimed only when no DROP failed.
    assert "Cleaned up" not in capsys.readouterr().out


def test_cleanup_success_prints_cleaned_up(module, capsys):
    conn, cursor = make_conn()
    module.cleanup(conn, [TARGET, STAGE])
    assert "Cleaned up" in capsys.readouterr().out


def test_probe_error_other_than_unknown_table_propagates(module):
    """A probe failure that is NOT table-not-found (e.g. a dead connection)
    must not be read as 'missing' — setup must abort without creating."""
    conn, cursor = make_conn(probe_error=ConnectionError("connection dead"))
    with pytest.raises(ConnectionError, match="connection dead"):
        module.setup_schema(conn)
    assert executed(cursor, "CREATE") == []
    assert executed(cursor, "DROP") == []


def test_main_clean_run_applies_two_snapshots_and_cleans_up(module, monkeypatch):
    conn, cursor = make_conn()
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    module.main()
    merges = executed(cursor, "MERGE INTO")
    assert len(merges) == 2
    drops = [table_of(d) for d in executed(cursor, "DROP TABLE")]
    assert drops == [STAGE, TARGET]
    conn.close.assert_called_once_with()


def test_main_merge_failure_preserves_original_error_when_cleanup_fails(
    module, monkeypatch, capsys
):
    conn, cursor = make_conn(fail_on="MERGE INTO", drop_fail={STAGE})
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="boom on MERGE") as excinfo:
        module.main()
    # The MERGE error — not the cleanup error — is what propagates.
    assert "boom on MERGE" in str(excinfo.value)
    assert "cleanup failed" not in str(excinfo.value)
    assert "cleanup failed" in capsys.readouterr().err  # warning, not replacement
    # The target table was still dropped despite the stage drop failing.
    assert TARGET in [table_of(d) for d in executed(cursor, "DROP TABLE")]


def test_main_refusal_drops_nothing(module, monkeypatch):
    conn, cursor = make_conn(existing={TARGET})
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="refusing to run"):
        module.main()
    assert executed(cursor, "DROP") == []
    conn.close.assert_called_once_with()
