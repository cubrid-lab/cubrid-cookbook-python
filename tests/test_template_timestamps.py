"""Offline guard: templates must store naive UTC timestamps and avoid ``utcnow``.

CUBRID ``DATETIME`` columns are naive, so every template stores naive UTC values
produced by ``datetime.now(timezone.utc).replace(tzinfo=None)``. The helpers are
executed here without importing the templates (no Flask/FastAPI install needed),
with the process timezone set away from UTC so a helper built on local time fails.
"""

from __future__ import annotations

import ast
import os
import re
import time
import unittest
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
HELPER_NAMES = {"naive_utc_now", "utcnow_naive", "utcnow"}
HELPER_FILES = {"models.py", "app.py", "routes.py"}
HELPER_DEF = re.compile(r"^def (%s)\(" % "|".join(sorted(HELPER_NAMES)), re.MULTILINE)
TOLERANCE = timedelta(seconds=5)


def _py_files() -> list[Path]:
    return sorted(p for p in TEMPLATES.rglob("*.py") if ".venv" not in p.parts)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _helpers(path: Path) -> list[ast.FunctionDef]:
    return [
        n for n in _tree(path).body if isinstance(n, ast.FunctionDef) and n.name in HELPER_NAMES
    ]


def _datetime_imports(path: Path) -> list[ast.stmt]:
    return [n for n in _tree(path).body if isinstance(n, ast.ImportFrom) and n.module == "datetime"]


def _load_helpers(path: Path) -> dict[str, object]:
    """Execute a file's datetime imports and helper functions, return the namespace."""
    namespace: dict[str, object] = {}
    sources = [path]
    if path.name == "routes.py" and (path.parent / "models.py").exists():
        sources.insert(0, path.parent / "models.py")  # routes helpers may delegate to models
    for source in sources:
        module = ast.Module(body=[*_datetime_imports(source), *_helpers(source)], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), namespace)  # noqa: S102
    return namespace


class TemplateTimestampTests(unittest.TestCase):
    def test_no_utcnow_attribute_on_any_base(self) -> None:
        offenders = []
        for path in _py_files():
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Attribute) and node.attr == "utcnow":
                    offenders.append(f"{path.relative_to(TEMPLATES)}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_helper_set_matches_files(self) -> None:
        by_regex = {
            p
            for p in _py_files()
            if p.name in HELPER_FILES and HELPER_DEF.search(p.read_text(encoding="utf-8"))
        }
        by_ast = {p for p in _py_files() if p.name in HELPER_FILES and _helpers(p)}
        self.assertEqual(by_regex, by_ast)
        self.assertTrue(by_ast, "no timestamp helpers found under templates/")

    def test_helpers_return_current_naive_utc(self) -> None:
        old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Seoul"  # a local-time helper would be 9 hours off
        time.tzset()
        self.addCleanup(self._restore_tz, old_tz)

        checked = 0
        for path in _py_files():
            if path.name not in HELPER_FILES or not _helpers(path):
                continue
            namespace = _load_helpers(path)
            for func in _helpers(path):
                with self.subTest(helper=f"{path.relative_to(TEMPLATES)}:{func.name}"):
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", DeprecationWarning)
                        value = namespace[func.name]()  # type: ignore[operator]
                    expected = datetime.now(timezone.utc).replace(tzinfo=None)
                    self.assertIsNone(value.tzinfo)
                    self.assertLess(abs(value - expected), TOLERANCE)
                    checked += 1
        self.assertGreater(checked, 0)

    @staticmethod
    def _restore_tz(old_tz: str | None) -> None:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


if __name__ == "__main__":
    unittest.main()
