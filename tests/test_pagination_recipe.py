"""Offline tests for the pagination recipe (fundamentals/pycubrid/19_pagination.py).

A fake cursor records the SQL and parameters each page function binds, so the
tests need no live CUBRID server. Invalid pages must be rejected before any
database call is made.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

try:
    import pycubrid  # noqa: F401
except ImportError:  # the recipe only calls pycubrid.connect() from its __main__ block
    sys.modules["pycubrid"] = types.ModuleType("pycubrid")

_RECIPE = Path(__file__).resolve().parents[1] / "fundamentals" / "pycubrid" / "19_pagination.py"
_SPEC = importlib.util.spec_from_file_location("_cookbook_pagination", _RECIPE)
assert _SPEC is not None and _SPEC.loader is not None
pagination = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pagination)


class FakeCursor:
    """Records execute() calls and returns canned rows from fetchall()."""

    def __init__(self, rows: list[tuple[int, str]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, tuple[int, int]]] = []

    def execute(self, sql: str, params: tuple[int, int]) -> None:
        self.calls.append((sql, params))

    def fetchall(self) -> list[tuple[int, str]]:
        return self._rows


ROWS = [(1, "item-01"), (2, "item-02"), (3, "item-03")]


@pytest.mark.parametrize("page", [0, -1, -100])
@pytest.mark.parametrize("page_function", ["page_with_limit_offset", "page_with_orderby_num"])
def test_invalid_page_is_rejected_before_any_database_call(page: int, page_function: str) -> None:
    cursor = FakeCursor(ROWS)

    with pytest.raises(ValueError, match="page must be 1 or greater"):
        getattr(pagination, page_function)(cursor, page)

    assert cursor.calls == []


@pytest.mark.parametrize(
    ("page", "expected_params"),
    [(1, (3, 0)), (2, (3, 3)), (3, (3, 6))],
)
def test_limit_offset_binds_the_same_params_as_before(
    page: int, expected_params: tuple[int, int]
) -> None:
    cursor = FakeCursor(ROWS)

    assert pagination.page_with_limit_offset(cursor, page) == ROWS
    assert [params for _sql, params in cursor.calls] == [expected_params]


@pytest.mark.parametrize(
    ("page", "expected_params"),
    [(1, (1, 3)), (2, (4, 6)), (3, (7, 9))],
)
def test_orderby_num_binds_the_same_params_as_before(
    page: int, expected_params: tuple[int, int]
) -> None:
    cursor = FakeCursor(ROWS)

    assert pagination.page_with_orderby_num(cursor, page) == ROWS
    assert [params for _sql, params in cursor.calls] == [expected_params]
