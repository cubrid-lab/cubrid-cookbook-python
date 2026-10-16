"""Evaluator-owned checks for the isolation-levels-mvcc task (#54).

The recipe runs against a fake ``pycubrid`` that records every statement, so no
database is needed. This shows which SQL the recipe sends, not that a live CUBRID
accepts it. Copied into the candidate's worktree only by ``scripts/agent_eval.py run``.
"""

from __future__ import annotations

import re
import runpy
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "fundamentals" / "isolation-levels" / "01_isolation_levels.py"
GOLDEN = RECIPE.parent / "expected" / "01_isolation_levels.expected"
MVCC = {"READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}


class _Cursor:
    def __init__(self, log):
        self.log = log
        self.description = None
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.log.append(" ".join(str(sql).split()))

    def fetchone(self):
        return (4,)

    def fetchall(self):
        return []

    def __iter__(self):
        return iter([])

    def close(self):
        pass


class _Connection:
    def __init__(self, log):
        self.log = log
        self.autocommit = False

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def set_autocommit(self, value):
        self.autocommit = value


def _statements(monkeypatch):
    log = []
    fake = types.ModuleType("pycubrid")
    fake.connect = lambda *args, **kwargs: _Connection(log)
    fake.Error = Exception
    fake.DatabaseError = Exception
    fake.OperationalError = Exception
    monkeypatch.setitem(sys.modules, "pycubrid", fake)
    try:
        runpy.run_path(str(RECIPE), run_name="__main__")
    except SystemExit:
        pass
    return log


def test_only_mvcc_level_names_are_set(monkeypatch):
    levels = [
        m.group(1).strip().upper()
        for sql in _statements(monkeypatch)
        if (m := re.match(r"SET TRANSACTION ISOLATION LEVEL (.+)", sql, re.I))
    ]
    assert levels, "the recipe sets no isolation level"
    assert set(levels) <= MVCC, levels
    assert set(levels) == MVCC, "every MVCC level is demonstrated"


def test_the_recipe_has_a_golden():
    assert GOLDEN.is_file() and GOLDEN.read_text(encoding="utf-8").strip()
