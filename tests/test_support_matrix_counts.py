"""Offline checks for scripts/check_support_matrix_counts.py."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_support_matrix_counts", ROOT / "scripts/check_support_matrix_counts.py"
)
counts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(counts)
MATRIX = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")


class SupportMatrixCountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for src in ("fundamentals", "migration", "pitfalls", "quickstart", "templates"):
            shutil.copytree(ROOT / src, self.tmp / src, ignore=shutil.ignore_patterns("*.pyc"))

    def test_repository_matches_table(self) -> None:
        self.assertEqual(counts.check(ROOT, MATRIX), [])

    def test_stray_files_and_dirs_do_not_count(self) -> None:
        (self.tmp / "templates/flask/NOTES.md").write_text("x")
        (self.tmp / "templates/flask/scratch").mkdir()
        (self.tmp / "templates/dashboard/helpers.py").write_text("x")
        self.assertEqual(counts.check(self.tmp, MATRIX), [])

    def test_new_flask_suite_is_reported(self) -> None:
        (self.tmp / "templates/flask/99-new/tests").mkdir(parents=True)
        errors = counts.check(self.tmp, MATRIX)
        self.assertIn("row 'Flask templates': table says 11, repository has 12", errors)

    def test_unmapped_golden_is_reported(self) -> None:
        golden = self.tmp / "fundamentals/new-topic/expected/01_new.expected"
        golden.parent.mkdir(parents=True)
        golden.write_text("x")
        errors = counts.check(self.tmp, MATRIX)
        self.assertIn(
            "golden fundamentals/new-topic/expected/01_new.expected is not counted by any table row",
            errors,
        )

    def test_wrong_total_and_unknown_row_are_reported(self) -> None:
        matrix = MATRIX.replace("| **Total** | **105** |", "| **Total** | **107** |").replace(
            "| Django template | 1 |", "| Django app | 1 |"
        )
        errors = counts.check(ROOT, matrix)
        self.assertIn(
            "row 'Django app': no counting rule; add one to check_support_matrix_counts.py", errors
        )
        self.assertIn("row 'Django template' is missing from the table", errors)
        self.assertTrue(any(e.startswith("**Total** row says 107") for e in errors), errors)

    def test_duplicate_and_short_rows_are_reported(self) -> None:
        row = "| SQLAlchemy quickstart | 1 | `make verify` (CI, 11.2 + 11.4) |\n"
        matrix = MATRIX.replace(row, row + row + "| Django template | 1 |\n", 1)
        errors = counts.check(
            ROOT, matrix.replace("| **Total** | **105** |", "| **Total** | **106** |")
        )
        self.assertIn("row 'SQLAlchemy quickstart' appears more than once", errors)
        self.assertIn("row 'Django template': expected 3 cells, found 2", errors)

    def test_stale_golden_counts_are_reported(self) -> None:
        next((self.tmp / "fundamentals/pycubrid/expected").glob("*.expected")).unlink()
        errors = counts.check(self.tmp, MATRIX)
        self.assertIn("row 'pycubrid fundamentals': table says 22, repository has 21", errors)
        self.assertIn("**Total** row says 69 golden-backed, repository has 68", errors)

    def test_missing_table_and_total_are_reported(self) -> None:
        self.assertEqual(
            counts.check(ROOT, "no table"),
            [f"Recipe Coverage table header not found: {counts.TABLE_HEADER!r}"],
        )
        total = next(line for line in MATRIX.splitlines() if line.startswith("| **Total**"))
        self.assertIn(
            "**Total** row is missing", counts.check(ROOT, MATRIX.replace(total + "\n", ""))
        )

    def test_sqlalchemy_range_matches_reviewed_dialect_range(self) -> None:
        self.assertEqual(counts.check_sqlalchemy_range(ROOT, MATRIX), [])

    def test_promoting_sqlalchemy_2_2_in_the_row_is_rejected(self) -> None:
        promoted = MATRIX.replace("| SQLAlchemy | 2.0, 2.1 |", "| SQLAlchemy | 2.0–2.2 |")
        self.assertNotEqual(promoted, MATRIX)
        errors = counts.check_sqlalchemy_range(ROOT, promoted)
        self.assertTrue(any(e.startswith("SQLAlchemy row says '2.0–2.2'") for e in errors), errors)

    def test_changing_only_the_row_status_is_rejected(self) -> None:
        promoted = MATRIX.replace("; 2.2 is not supported (see below)", "; 2.2 supported")
        self.assertNotEqual(promoted, MATRIX)
        self.assertEqual(
            counts.check_sqlalchemy_range(ROOT, promoted),
            ["SQLAlchemy row status differs from the reviewed wording"],
        )

    def test_promoting_sqlalchemy_2_2_in_a_claim_file_is_rejected(self) -> None:
        for name in counts.SQLALCHEMY_CLAIMS:
            for promoted in ("2.0/2.1/2.2", "2.0–2.2", "2.0–2.3", "2.0, 2.1 and 2.2", "2.0~2.2"):
                with self.subTest(name=name, promoted=promoted):
                    for src in ("README.md", "docs/README.ko.md", "docs/index.md", "llms.txt"):
                        (self.tmp / src).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(ROOT / src, self.tmp / src)
                    cfg = self.tmp / ".github/ISSUE_TEMPLATE/config.yml"
                    cfg.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(ROOT / ".github/ISSUE_TEMPLATE/config.yml", cfg)
                    path = self.tmp / name
                    path.write_text(path.read_text().replace("2.0/2.1", promoted))
                    errors = counts.check_sqlalchemy_range(self.tmp, MATRIX)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertTrue(errors[0].startswith(f"{name} must say"), errors)


ROW_1110 = (
    "| sqlalchemy-cubrid | 1.11.0 | `sqlalchemy>=2.0,<2.2` |"
    " `sqlalchemy_cubrid-1.11.0-py3-none-any.whl` SHA-256"
    " `594ec50a6294dea5f40dcd557e806af9fb7d8555f6728acf90a774c1d7f355cc` | 2026-10-16 |"
)


class PublishedRequirementTests(unittest.TestCase):
    """#393: published-requirement rows are facts about one published artifact."""

    def with_row(self, row: str) -> str:
        self.assertIn(ROW_1110, MATRIX)
        return MATRIX.replace(ROW_1110, row + "\n" + ROW_1110)

    def test_current_matrix_records_only_verified_artifacts(self) -> None:
        self.assertEqual(counts.check_published_requirements(MATRIX), [])

    def test_a_new_published_artifact_after_an_old_observation_is_accepted(self) -> None:
        newer = (
            "| sqlalchemy-cubrid | 1.12.0 | `sqlalchemy>=2.0,<2.2` |"
            " `sqlalchemy_cubrid-1.12.0-py3-none-any.whl` SHA-256 `" + "a" * 64 + "` | 2026-11-02 |"
        )
        self.assertEqual(counts.check_published_requirements(self.with_row(newer)), [])

    def test_the_dated_record_is_history_and_not_checked(self) -> None:
        record = MATRIX.split("### Dated record: 2026-10-11", 1)[1].split("\n## ", 1)[0]
        self.assertIn("unreleased `main`", record)
        self.assertEqual(counts.check_published_requirements(MATRIX), [])

    def test_unpublished_or_unverified_rows_are_rejected(self) -> None:
        for row in (
            # an abandoned / main-only version
            "| sqlalchemy-cubrid | 1.11.1 | `sqlalchemy>=2.0,<2.2` | unreleased `main` at `37d0b0b` | 2026-10-16 |",
            "| sqlalchemy-cubrid | 1.11.2 | `sqlalchemy>=2.0,<2.2` | release candidate #910 | 2026-10-16 |",
            # a failed lookup
            "| pycubrid | 1.14.0 | not verified | PyPI lookup failed | 2026-10-16 |",
        ):
            with self.subTest(row=row):
                errors = counts.check_published_requirements(self.with_row(row))
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("is not a fact", errors[0])

    def test_rows_without_artifact_evidence_are_rejected(self) -> None:
        cases = {
            "evidence must give the wheel's SHA-256": (
                "| pycubrid | 1.13.0 | `x` | `pycubrid-1.13.0-py3-none-any.whl` | 2026-10-16 |"
            ),
            "evidence must name its wheel": (
                "| pycubrid | 1.13.0 | `x` | `other-1.13.0-py3-none-any.whl` SHA-256 `"
                + "b" * 64
                + "` | 2026-10-16 |"
            ),
            "version must be MAJOR.MINOR.PATCH": (
                "| pycubrid | 1.13 | `x` | `pycubrid-1.13-py3-none-any.whl` SHA-256 `"
                + "b" * 64
                + "` | 2026-10-16 |"
            ),
            "checked date must be YYYY-MM-DD": (
                "| pycubrid | 1.13.0 | `x` | `pycubrid-1.13.0-py3-none-any.whl` SHA-256 `"
                + "b" * 64
                + "` | October |"
            ),
        }
        for message, row in cases.items():
            with self.subTest(message=message):
                errors = counts.check_published_requirements(self.with_row(row))
                self.assertTrue(any(message in e for e in errors), errors)

    def test_a_missing_section_fails(self) -> None:
        stripped = MATRIX.replace(counts.PUBLISHED_HEADING, "### Something else")
        self.assertEqual(
            counts.check_published_requirements(stripped),
            [f"missing '{counts.PUBLISHED_HEADING}' section"],
        )


if __name__ == "__main__":
    unittest.main()
