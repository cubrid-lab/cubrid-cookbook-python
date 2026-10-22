"""Unit tests for scripts/example_requirements.py."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import example_requirements  # noqa: E402


class RequirementNamesTests(unittest.TestCase):
    def test_requirement_names_skips_comments_options_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            content = (
                "# top\n"
                "pytest>=8  # c\n"
                "\n"
                "-r base.txt\n"
                "sqlalchemy-cubrid[pycubrid]==1\n"
                "  Foo_bar.baz ; python_version<'3.12'\n"
            )
            req_file.write_text(content, encoding="utf-8")
            names = example_requirements.requirement_names(req_file)
            self.assertEqual(names, ["pytest", "sqlalchemy-cubrid", "Foo_bar.baz"])

    def test_empty_requirements_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_file = Path(tmp) / "requirements.txt"
            req_file.write_text("# only comments\n\n", encoding="utf-8")
            self.assertEqual(example_requirements.requirement_names(req_file), [])


class MissingDistributionsTests(unittest.TestCase):
    def test_missing_distributions_reports_uninstalled_packages_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            req_file = golden / "requirements.txt"
            req_file.write_text(
                "installed-pkg>=1.0\nmissing-pkg==2.0\n",
                encoding="utf-8",
            )

            def fake_distribution(name: str):
                if name == "installed-pkg":
                    return mock.MagicMock()
                raise metadata.PackageNotFoundError(name)

            with mock.patch.object(
                example_requirements.metadata, "distribution", side_effect=fake_distribution
            ):
                missing = example_requirements.missing_distributions([root])

            expected_path = req_file.as_posix()
            self.assertEqual(missing, [f"missing-pkg ({expected_path})"])

    def test_missing_distributions_deduplicates_repeated_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            req_file = golden / "requirements.txt"
            req_file.write_text("pkg\npkg\n", encoding="utf-8")

            with mock.patch.object(
                example_requirements.metadata,
                "distribution",
                side_effect=metadata.PackageNotFoundError("pkg"),
            ):
                missing = example_requirements.missing_distributions([root])

            self.assertEqual(len(missing), 1)
            self.assertEqual(missing, [f"pkg ({req_file.as_posix()})"])

    def test_all_examples_also_require_the_suite_test_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "templates" / "app"
            suite.mkdir(parents=True)
            req_file = suite / "requirements.txt"
            req_file.write_text("framework\n", encoding="utf-8")

            def fake_distribution(name: str):
                if name == "pytest":
                    return mock.MagicMock()
                raise metadata.PackageNotFoundError(name)

            with mock.patch.object(
                example_requirements.metadata, "distribution", side_effect=fake_distribution
            ):
                golden_only = example_requirements.missing_distributions([root])
                every = example_requirements.missing_distributions([root], every=True)

            self.assertEqual(golden_only, [])
            self.assertEqual(
                every,
                [f"framework ({req_file.as_posix()})", "pytest-asyncio (live pytest suites)"],
            )


class MainCheckTests(unittest.TestCase):
    def test_main_check_returns_one_and_reports_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            (golden / "requirements.txt").write_text("missing-lib\n", encoding="utf-8")

            with (
                mock.patch.object(
                    example_requirements.metadata,
                    "distribution",
                    side_effect=metadata.PackageNotFoundError("missing-lib"),
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = example_requirements.main(["--check", str(root)])

            self.assertEqual(exit_code, 1)
            err_output = stderr.getvalue()
            self.assertIn("Missing example dependencies: run `make deps` first.", err_output)
            self.assertIn("✗ missing-lib", err_output)

    def test_main_check_returns_zero_when_dependencies_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "example"
            golden.mkdir()
            (golden / "expected").mkdir()
            (golden / "requirements.txt").write_text("present-lib\n", encoding="utf-8")

            with (
                mock.patch.object(
                    example_requirements.metadata,
                    "distribution",
                    return_value=mock.MagicMock(),
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = example_requirements.main(["--check", str(root)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")

    def test_main_check_returns_zero_for_empty_or_non_golden_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(example_requirements.main(["--check", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
