"""Offline tests for the page checks in fundamentals/pycubrid/19_pagination.py."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "fundamentals" / "pycubrid" / "19_pagination.py"


class FakeCursor:
    """Records execute() calls instead of talking to a database."""

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return []


@pytest.fixture(scope="module")
def pagination(monkeypatch_module):
    # The recipe imports pycubrid at module level; a stub keeps this offline.
    monkeypatch_module.setitem(sys.modules, "pycubrid", types.ModuleType("pycubrid"))
    spec = importlib.util.spec_from_file_location("pagination_recipe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def monkeypatch_module():
    patcher = pytest.MonkeyPatch()
    yield patcher
    patcher.undo()


@pytest.mark.parametrize(
    ("page", "expected"),
    [(1, (3, 0)), (2, (3, 3)), (3, (3, 6))],
)
def test_limit_offset_binds_page_size_and_offset(pagination, page, expected):
    cursor = FakeCursor()
    pagination.page_with_limit_offset(cursor, page)
    assert cursor.calls[0][1] == expected


@pytest.mark.parametrize(
    ("page", "expected"),
    [(1, (1, 3)), (2, (4, 6)), (3, (7, 9))],
)
def test_orderby_num_binds_inclusive_range(pagination, page, expected):
    cursor = FakeCursor()
    pagination.page_with_orderby_num(cursor, page)
    assert cursor.calls[0][1] == expected


@pytest.mark.parametrize("page", [0, -1, True, 1.5, "2"])
@pytest.mark.parametrize("function", ["page_with_limit_offset", "page_with_orderby_num"])
def test_invalid_page_is_rejected_before_any_query(pagination, function, page):
    cursor = FakeCursor()
    with pytest.raises(ValueError, match="positive integer"):
        getattr(pagination, function)(cursor, page)
    assert cursor.calls == []
