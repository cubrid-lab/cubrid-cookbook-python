"""Offline checks for scripts/check_dependency_floors.py (#152)."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_dependency_floors", ROOT / "scripts/check_dependency_floors.py"
)
floors = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(floors)
MATRIX = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")


class DependencyFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for src in ("fundamentals", "migration", "pitfalls", "quickstart", "templates"):
            shutil.copytree(ROOT / src, self.tmp / src, ignore=shutil.ignore_patterns("*.pyc"))

    def test_repository_matches_documented_contract(self) -> None:
        self.assertEqual(floors.check(ROOT, MATRIX), [])

    def test_bare_driver_requirement_is_rejected(self) -> None:
        target = self.tmp / "quickstart/5min-sqlalchemy/requirements.txt"
        target.write_text("pycubrid\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("no version floor" in e and "pycubrid" in e for e in errors), errors)

    def test_below_global_floor_is_rejected(self) -> None:
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=0.5\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )

    def test_undocumented_custom_floor_is_rejected(self) -> None:
        # A higher, undocumented pin is drift too -- it must be added as an
        # exception (and documented in SUPPORT_MATRIX.md), not pinned ad hoc.
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=1.9\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )

    def test_global_floor_rejects_an_unexpected_upper_bound(self) -> None:
        # The documented global floor is one-sided (>=X.Y, no ceiling); a
        # correct-looking lower bound with a smuggled upper bound is still
        # drift from the documented contract.
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=1.6.1,<1.7\nsqlalchemy-cubrid>=1.0,<1.1\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )
        self.assertTrue(
            any(
                "expected sqlalchemy-cubrid>=1.0, no upper bound (global floor)" in e
                for e in errors
            ),
            errors,
        )

    def test_advanced_sqlalchemy_floor_rejects_an_unexpected_upper_bound(self) -> None:
        target = self.tmp / "fundamentals/async/requirements.txt"
        text = target.read_text().replace(
            "sqlalchemy-cubrid>=1.4.2", "sqlalchemy-cubrid>=1.4.2,<1.5"
        )
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any(
                "expected sqlalchemy-cubrid>=1.4.2, no upper bound (advanced SQLAlchemy floor)" in e
                for e in errors
            ),
            errors,
        )

    def test_template_exception_wrong_floor_is_rejected(self) -> None:
        target = self.tmp / "templates/flask/requirements.txt"
        text = target.read_text().replace("pycubrid>=1.7,<2", "pycubrid>=1.6.1")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.7,<2 (template floor)" in e for e in errors), errors
        )

    def test_fundamentals_pycubrid_exact_floor_is_enforced(self) -> None:
        target = self.tmp / "fundamentals/pycubrid/requirements.txt"
        target.write_text("pycubrid>=1.7,<2\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected pycubrid>=1.9,<2" in e for e in errors), errors)

    def test_fundamentals_sqlalchemy_collection_floors_are_enforced(self) -> None:
        target = self.tmp / "fundamentals/sqlalchemy/requirements.txt"
        target.write_text("sqlalchemy>=2.0\npycubrid>=1.8,<2\nsqlalchemy-cubrid>=1.4.2\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected pycubrid>=1.9,<2" in e for e in errors), errors)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.9 in" in e for e in errors), errors)

    def test_fundamentals_alembic_exact_sqlalchemy_floor_is_enforced(self) -> None:
        target = self.tmp / "fundamentals/alembic/requirements.txt"
        text = target.read_text().replace("sqlalchemy-cubrid>=1.8", "sqlalchemy-cubrid>=1.0")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.8 in" in e for e in errors), errors)

    def test_fundamentals_alembic_rejects_sqlalchemy_floor_above_exact(self) -> None:
        target = self.tmp / "fundamentals/alembic/requirements.txt"
        text = target.read_text().replace("sqlalchemy-cubrid>=1.8", "sqlalchemy-cubrid>=1.9")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.8 in" in e for e in errors), errors)

    def test_stale_alembic_exception_directory_is_reported(self) -> None:
        shutil.rmtree(self.tmp / "fundamentals/alembic")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("fundamentals/alembic" in e and "no longer exists" in e for e in errors), errors
        )

    def test_stale_exception_directory_is_reported(self) -> None:
        shutil.rmtree(self.tmp / "fundamentals/pycubrid")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("fundamentals/pycubrid" in e and "no longer exists" in e for e in errors), errors
        )

    def test_missing_global_floor_in_matrix_is_reported(self) -> None:
        matrix = MATRIX.replace("| pycubrid | ≥ 1.6.1 |", "| pycubrid | removed |")
        errors = floors.check(ROOT, matrix)
        self.assertIn("SUPPORT_MATRIX.md: no global floor found for 'pycubrid'", errors)


if __name__ == "__main__":
    unittest.main()
