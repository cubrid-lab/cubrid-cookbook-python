"""Offline regression tests for the ENUM lesson's invalid-value check.

The lesson claims CUBRID rejects a value outside the declared ENUM. These tests
use a fake driver to prove the lesson fails when that claim is false and does not
treat unrelated driver errors as proof of the ENUM constraint.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RECIPE = Path(__file__).resolve().parents[1] / "fundamentals/pycubrid/21_enum_type.py"


def _fake_pycubrid() -> types.ModuleType:
    """A minimal pycubrid exposing the DB-API exception hierarchy."""
    module = types.ModuleType("pycubrid")
    module.Error = type("Error", (Exception,), {})
    module.DatabaseError = type("DatabaseError", (module.Error,), {})
    for name in (
        "DataError",
        "IntegrityError",
        "OperationalError",
        "ProgrammingError",
    ):
        setattr(module, name, type(name, (module.DatabaseError,), {}))
    module.connect = MagicMock()
    return module


@pytest.fixture
def fake_driver(monkeypatch):
    module = _fake_pycubrid()
    monkeypatch.setitem(sys.modules, "pycubrid", module)
    return module


@pytest.fixture
def recipe(fake_driver):
    spec = importlib.util.spec_from_file_location("enum_type_recipe", RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejected_value_is_the_expected_teaching_result(recipe, fake_driver, capsys):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = fake_driver.ProgrammingError("invalid enum value")

    recipe.reject_invalid(cursor, conn)

    assert "rejected by ENUM constraint: ProgrammingError" in capsys.readouterr().out
    conn.rollback.assert_called_once_with()
    conn.commit.assert_not_called()


def test_unexpected_success_fails_the_lesson_and_rolls_back(recipe, capsys):
    conn = MagicMock()
    cursor = MagicMock()

    with pytest.raises(RuntimeError, match="rejection was not verified"):
        recipe.reject_invalid(cursor, conn)

    assert "rejected by ENUM constraint" not in capsys.readouterr().out
    conn.rollback.assert_called_once_with()
    conn.commit.assert_not_called()


def test_unrelated_driver_failure_is_not_reported_as_a_rejection(recipe, fake_driver, capsys):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = fake_driver.OperationalError("connection lost")

    with pytest.raises(fake_driver.OperationalError):
        recipe.reject_invalid(cursor, conn)

    assert "rejected by ENUM constraint" not in capsys.readouterr().out


def test_script_exits_with_an_error_and_still_cleans_up_when_the_enum_accepts_it(fake_driver):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = []
    fake_driver.connect.return_value = conn

    with pytest.raises(RuntimeError, match="rejection was not verified"):
        runpy.run_path(str(RECIPE), run_name="__main__")

    drops = [c.args[0] for c in cursor.execute.call_args_list if "DROP TABLE" in c.args[0]]
    assert len(drops) == 2  # setup and cleanup
    conn.close.assert_called_once_with()
