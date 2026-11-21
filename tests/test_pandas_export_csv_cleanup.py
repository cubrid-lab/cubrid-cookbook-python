"""Offline check: the pandas CSV recipe keeps its primary error when cleanup fails (#580).

Runs ``fundamentals/pandas/06_export_csv.py`` with a mocked engine and
``DataFrame.to_csv``; no CUBRID database is touched.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "fundamentals" / "pandas" / "06_export_csv.py"


def load_recipe():
    spec = importlib.util.spec_from_file_location("pandas_export_csv_recipe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_engine(drop_fails: bool) -> mock.MagicMock:
    """Engine whose first begin() (seed) works and whose last begin() (drop) may fail."""
    engine = mock.MagicMock()
    ok = mock.MagicMock()
    calls = {"n": 0}

    def begin():
        calls["n"] += 1
        # Call 1 seeds the table, call 2 is the cleanup drop.
        if drop_fails and calls["n"] == 2:
            raise RuntimeError("connection lost")
        return ok

    engine.begin.side_effect = begin
    return engine


class ExportCleanupTests(unittest.TestCase):
    def run_main(self, *, to_csv_error, drop_fails):
        recipe = load_recipe()
        engine = make_engine(drop_fails)
        frame = pd.DataFrame(
            {
                "sale_month": ["2026-01"],
                "category_name": ["office"],
                "revenue_cents": [100],
                "is_promo": [1],
            }
        )
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(recipe, "create_engine", return_value=engine),
            mock.patch.object(recipe.pd, "read_sql", return_value=frame),
            mock.patch.object(pd.DataFrame, "to_csv", side_effect=to_csv_error),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = recipe.main()
        return code, out.getvalue(), err.getvalue(), engine

    def test_export_failure_and_cleanup_failure(self):
        code, out, err, engine = self.run_main(to_csv_error=IOError("disk full"), drop_fails=True)
        self.assertEqual(code, 1)
        self.assertIn("CSV export error: disk full", out)
        self.assertIn("Cleanup error", err)
        self.assertIn("connection lost", err)
        engine.dispose.assert_called_once_with()

    def test_export_failure_with_working_cleanup(self):
        code, out, err, engine = self.run_main(to_csv_error=IOError("disk full"), drop_fails=False)
        self.assertEqual(code, 1)
        self.assertIn("CSV export error: disk full", out)
        self.assertEqual(err, "")
        engine.dispose.assert_called_once_with()

    def test_success_with_failing_cleanup_is_not_success(self):
        code, _, err, engine = self.run_main(to_csv_error=None, drop_fails=True)
        self.assertEqual(code, 1)
        self.assertIn("Cleanup error", err)
        engine.dispose.assert_called_once_with()

    def test_happy_path(self):
        code, out, err, engine = self.run_main(to_csv_error=None, drop_fails=False)
        self.assertEqual(code, 0)
        self.assertIn("CSV exported to:", out)
        self.assertEqual(err, "")
        engine.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
