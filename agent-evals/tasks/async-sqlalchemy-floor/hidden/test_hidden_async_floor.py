"""Evaluator-owned checks for the async-sqlalchemy-floor task (#94).

The async ``cubrid+aiopycubrid://`` dialect is first installable from PyPI in
sqlalchemy-cubrid 1.2.3. These checks read the requirement, the recipe's printed
requirement, its golden and the support matrix; they install nothing and need no
database. Copied into the candidate's worktree only by ``scripts/agent_eval.py run``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE_DIR = ROOT / "fundamentals" / "async"
FIRST_ASYNC = (1, 2, 3)
FLOOR = re.compile(r"sqlalchemy-cubrid(?:\[[^\]]*\])?\s*>=\s*([0-9][0-9.]*)", re.I)


def _version(text):
    return tuple(int(part) for part in text.split("."))


def _floor():
    # Only an active requirement line counts, never a comment that mentions one.
    text = (RECIPE_DIR / "requirements.txt").read_text(encoding="utf-8")
    match = next(
        (FLOOR.match(line.strip()) for line in text.splitlines() if FLOOR.match(line.strip())), None
    )
    assert match, "requirements.txt pins no sqlalchemy-cubrid floor"
    return match.group(1)


def test_the_floor_covers_the_async_dialect():
    assert _version(_floor()) >= FIRST_ASYNC


def test_printed_requirement_and_golden_match_the_floor():
    floor = _floor()
    tree = ast.parse((RECIPE_DIR / "02_async_sqlalchemy.py").read_text(encoding="utf-8"))
    printed = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("Requirements:")
    ]
    assert printed and all(FLOOR.search(t).group(1) == floor for t in printed), printed
    golden = (RECIPE_DIR / "expected" / "02_async_sqlalchemy.expected").read_text(encoding="utf-8")
    lines = [line for line in golden.splitlines() if line.startswith("Requirements:")]
    assert lines and all(FLOOR.search(line).group(1) == floor for line in lines), lines


def test_the_support_matrix_states_the_async_floor():
    floor = _floor()
    text = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
    assert any(
        floor in line and re.search(r"async|aiopycubrid", line, re.I) for line in text.splitlines()
    ), f"SUPPORT_MATRIX.md does not tie {floor} to the async recipe"
