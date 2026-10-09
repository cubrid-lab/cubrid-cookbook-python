"""Offline guard: templates must not use deprecated ``datetime.utcnow``.

CUBRID ``DATETIME`` columns are naive, so every template stores naive UTC values
produced by ``datetime.now(timezone.utc).replace(tzinfo=None)``. The helpers are
checked here without importing the templates (no Flask/FastAPI install needed).
"""

from __future__ import annotations

import ast
import unittest
import warnings
from datetime import datetime, timedelta
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
HELPER_NAMES = {"naive_utc_now", "utcnow_naive"}


def _py_files() -> list[Path]:
    return sorted(p for p in TEMPLATES.rglob("*.py") if ".venv" not in p.parts)


def _helpers(path: Path) -> list[ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in HELPER_NAMES]


class TemplateTimestampTests(unittest.TestCase):
    def test_no_deprecated_utcnow_attribute(self) -> None:
        offenders = []
        for path in _py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "utcnow"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "datetime"
                ):
                    offenders.append(f"{path.relative_to(TEMPLATES)}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_model_helpers_return_naive_utc_without_warnings(self) -> None:
        models = [p for p in _py_files() if p.name == "models.py" and _helpers(p)]
        self.assertGreaterEqual(len(models), 14)
        for path in models:
            for func in _helpers(path):
                namespace: dict[str, object] = {}
                source = "from datetime import datetime, timezone\n" + ast.unparse(func)
                exec(compile(source, str(path), "exec"), namespace)  # noqa: S102
                with warnings.catch_warnings():
                    warnings.simplefilter("error", DeprecationWarning)
                    value = namespace[func.name]()  # type: ignore[operator]
                self.assertIsNone(value.tzinfo, path)
                # Must compare with naive values read back from CUBRID without TypeError.
                self.assertLess(value - datetime(2000, 1, 1), timedelta(days=365 * 200))


if __name__ == "__main__":
    unittest.main()
