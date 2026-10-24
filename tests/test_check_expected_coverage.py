"""Unit tests for scripts/check_expected_coverage.py."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_expected_coverage as coverage  # noqa: E402


class RunnableExampleTests(unittest.TestCase):
    def test_init_file_is_not_runnable(self):
        self.assertFalse(coverage.is_runnable_example(Path("__init__.py")))

    def test_private_file_is_not_runnable(self):
        self.assertFalse(coverage.is_runnable_example(Path("_helper.py")))

    def test_normal_python_file_is_runnable(self):
        self.assertTrue(coverage.is_runnable_example(Path("example.py")))


class AllowlistTests(unittest.TestCase):
    def test_missing_allowlist_returns_empty_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.txt"

            with mock.patch.object(coverage, "ALLOWLIST_PATH", path):
                self.assertEqual(coverage.load_allowlist(), set())

    def test_valid_entry_with_reason_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.txt"
            path.write_text(
                "# Exclusions\n\nexamples/interactive.py  # requires user input\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "ALLOWLIST_PATH", path):
                self.assertEqual(
                    coverage.load_allowlist(),
                    {"examples/interactive.py"},
                )

    def test_entry_without_reason_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allowlist.txt"
            path.write_text("examples/interactive.py\n", encoding="utf-8")

            with mock.patch.object(coverage, "ALLOWLIST_PATH", path):
                with self.assertRaisesRegex(ValueError, "allowlist.txt:1"):
                    coverage.load_allowlist()

    def test_entry_with_empty_reason_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verify_exclusions.txt"
            path.write_text(
                "examples/demo.py  #   \n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "ALLOWLIST_PATH", path):
                with self.assertRaisesRegex(ValueError, r"verify_exclusions\.txt:1"):
                    coverage.load_allowlist()


class MissingGoldenTests(unittest.TestCase):
    def test_missing_golden_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            expected = example / "expected"
            expected.mkdir(parents=True)
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, ["examples/demo.py"])

    def test_existing_golden_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            expected = example / "expected"
            expected.mkdir(parents=True)
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )
            (expected / "demo.expected").write_text(
                "hello\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, [])

    def test_allowlisted_example_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            (example / "expected").mkdir(parents=True)
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], {"examples/demo.py"})

            self.assertEqual(result, [])

    def test_private_helper_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            example.mkdir()
            (example / "expected").mkdir()
            (example / "_helper.py").write_text("# helper\n", encoding="utf-8")
            (example / "__init__.py").write_text("", encoding="utf-8")

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, [])

    def test_folder_without_expected_directory_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            example.mkdir()
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, [])

    def test_expected_as_a_regular_file_does_not_opt_the_folder_in(self):
        # Only an expected/ DIRECTORY opts in: a file literally named
        # `expected` beside a script must not make that script "missing".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            example.mkdir()
            (example / "expected").write_text(  # a file, not a directory
                "not a directory\n",
                encoding="utf-8",
            )
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, [])

    def test_scripts_in_a_subfolder_without_their_own_expected_are_not_reported(self):
        # An expected/ directory opts in only the scripts directly beside it;
        # a nested folder without its own expected/ stays out.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            expected = example / "expected"
            expected.mkdir(parents=True)
            nested = example / "sub"
            nested.mkdir()
            (nested / "two.py").write_text(
                "print('two')\n",
                encoding="utf-8",
            )
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )
            (expected / "demo.expected").write_text(
                "hello\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, [])

    def test_only_expected_stem_suffix_counts_as_a_golden(self):
        # `expected/three.txt` is not a golden for `three.py`; a script whose
        # only "golden" has the wrong suffix is still reported as missing.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            expected = example / "expected"
            expected.mkdir(parents=True)
            (example / "three.py").write_text(
                "print('three')\n",
                encoding="utf-8",
            )
            (expected / "three.txt").write_text(
                "wrong suffix\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([example], set())

            self.assertEqual(result, ["examples/three.py"])

    def test_the_issue_repro_tree_reports_only_the_wrong_suffix_script(self):
        # One tree exercising all three rules at once: a file named `expected`
        # does not opt in, a subfolder script stays out, and only the
        # `.expected` suffix counts.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "a" / "expected").write_text(
                "not a directory\n",
                encoding="utf-8",
            )
            (root / "a" / "demo.py").write_text(
                "print('demo')\n",
                encoding="utf-8",
            )
            (root / "b" / "expected").mkdir(parents=True)
            (root / "b" / "sub").mkdir()
            (root / "b" / "sub" / "two.py").write_text(
                "print('two')\n",
                encoding="utf-8",
            )
            (root / "b" / "three.py").write_text(
                "print('three')\n",
                encoding="utf-8",
            )
            (root / "b" / "expected" / "three.txt").write_text(
                "wrong suffix\n",
                encoding="utf-8",
            )

            with mock.patch.object(coverage, "REPO_ROOT", root):
                result = coverage.find_missing([root], set())

            self.assertEqual(result, ["b/three.py"])


class MainTests(unittest.TestCase):
    def test_missing_golden_returns_exit_code_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "examples"
            (example / "expected").mkdir(parents=True)
            (example / "demo.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )
            allowlist = root / "scripts" / "verify_exclusions.txt"
            allowlist.parent.mkdir()
            allowlist.write_text("", encoding="utf-8")

            with (
                mock.patch.object(coverage, "REPO_ROOT", root),
                mock.patch.object(coverage, "ALLOWLIST_PATH", allowlist),
                mock.patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                result = coverage.main([])

            self.assertEqual(result, 1)
            self.assertIn("examples/demo.py", output.getvalue())

    def test_malformed_allowlist_returns_exit_code_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / "scripts" / "verify_exclusions.txt"
            allowlist.parent.mkdir()
            allowlist.write_text(
                "examples/demo.py\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(coverage, "REPO_ROOT", root),
                mock.patch.object(coverage, "ALLOWLIST_PATH", allowlist),
                mock.patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                result = coverage.main([])

            self.assertEqual(result, 1)
            self.assertIn("verify_exclusions.txt:1", output.getvalue())

    def test_main_returns_zero_when_no_goldens_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / "scripts" / "verify_exclusions.txt"
            allowlist.parent.mkdir()
            allowlist.write_text("# No exclusions\n", encoding="utf-8")

            with (
                mock.patch.object(coverage, "REPO_ROOT", root),
                mock.patch.object(coverage, "ALLOWLIST_PATH", allowlist),
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                result = coverage.main([])

            self.assertEqual(result, 0)

    def test_real_repository_passes(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(coverage.main([]), 0)


if __name__ == "__main__":
    unittest.main()
