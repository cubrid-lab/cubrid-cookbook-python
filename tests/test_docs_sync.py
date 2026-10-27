"""Unit tests for scripts/check_docs_sync.py (issues #182 and #174).

``pitfalls`` mixes a README-only landing page with example subdirectories
that ship real recipe code (``pitfalls/reserved-words/``, added in #181).
These tests pin the two behaviors #182 requires: a pitfalls example
subdirectory that contains code must be discovered and, if undocumented,
must fail the gate; a README-only pitfalls page (no code subdirectories)
must stay exempt and pass.

#174 adds the allowlist rule: every entry needs an inline ``# reason``, and a
malformed allowlist makes the gate exit non-zero.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_docs_sync  # noqa: E402
from scripts.check_docs_sync import (  # noqa: E402
    discover_examples,
    discover_nested_recipes,
    find_undocumented,
    find_untested,
    load_allowlist,
)


class PitfallsDiscoveryTests(unittest.TestCase):
    def test_pitfalls_example_with_code_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            example = repo_root / "pitfalls" / "reserved-words"
            example.mkdir(parents=True)
            (example / "01_reserved_words.py").write_text("# example\n")
            self.assertEqual(discover_examples(repo_root), ["pitfalls/reserved-words"])

    def test_readme_only_pitfalls_page_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            pitfalls = repo_root / "pitfalls"
            pitfalls.mkdir()
            (pitfalls / "README.md").write_text("# Pitfalls\n")
            self.assertEqual(discover_examples(repo_root), [])

    def test_pitfalls_subdir_without_code_is_not_an_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            pitfalls = repo_root / "pitfalls"
            notes = pitfalls / "notes"
            notes.mkdir(parents=True)
            (pitfalls / "README.md").write_text("# Pitfalls\n")
            (notes / "README.md").write_text("no example code here\n")
            self.assertEqual(discover_examples(repo_root), [])


class PitfallsGateTests(unittest.TestCase):
    """Exercise the same discover -> find_undocumented pipeline main() runs."""

    def _make_pitfalls_example(self, repo_root: Path) -> None:
        example = repo_root / "pitfalls" / "reserved-words"
        example.mkdir(parents=True)
        (example / "01_reserved_words.py").write_text("# example\n")

    def test_pitfalls_example_missing_from_llms_txt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._make_pitfalls_example(repo_root)
            examples = discover_examples(repo_root)
            llms_text = "quickstart/5min-fastapi is covered here.\n"
            self.assertEqual(find_undocumented(examples, llms_text), ["pitfalls/reserved-words"])

    def test_pitfalls_example_documented_in_llms_txt_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self._make_pitfalls_example(repo_root)
            examples = discover_examples(repo_root)
            llms_text = "See pitfalls/reserved-words for the live-verified recipe.\n"
            self.assertEqual(find_undocumented(examples, llms_text), [])

    def test_readme_only_pitfalls_page_passes_undocumented_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            pitfalls = repo_root / "pitfalls"
            pitfalls.mkdir()
            (pitfalls / "README.md").write_text("# Pitfalls\n")
            examples = discover_examples(repo_root)
            self.assertEqual(find_undocumented(examples, ""), [])


class NestedRecipeSmokeCoverageTests(unittest.TestCase):
    """A tested sibling must not hide an untested Flask or FastAPI recipe."""

    @staticmethod
    def make_recipe(root: Path, family: str, name: str, coverage: str | None = None) -> None:
        recipe = root / family / name
        recipe.mkdir(parents=True)
        (recipe / "app.py").write_text("# example\n", encoding="utf-8")
        if coverage:
            (recipe / coverage).mkdir()

    def test_nested_recipes_are_checked_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for family in ("templates/flask", "templates/api-service-fastapi/recipes"):
                self.make_recipe(root, family, "01-tested", "tests")
                self.make_recipe(root, family, "02-golden", "expected")
                self.make_recipe(root, family, "03-missing")
                notes = root / family / "04-docs-only"
                notes.mkdir()
                (notes / "README.md").write_text("no runnable code\n", encoding="utf-8")

            examples = discover_examples(root)
            self.assertEqual(find_untested(root, examples, set()), [])
            smoke_cases = [*examples, *discover_nested_recipes(root)]
            missing = find_untested(root, smoke_cases, set())
            self.assertEqual(
                missing,
                [
                    "templates/flask/03-missing",
                    "templates/api-service-fastapi/recipes/03-missing",
                ],
            )
            self.assertEqual(
                find_untested(root, smoke_cases, {"templates/flask/03-missing"}),
                ["templates/api-service-fastapi/recipes/03-missing"],
            )

    def test_main_warns_about_nested_missing_test_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_recipe(root, "templates/flask", "01-tested", "tests")
            self.make_recipe(root, "templates/flask", "02-missing")
            (root / "scripts").mkdir()
            (root / "README.md").write_text("templates/flask\n", encoding="utf-8")
            (root / "llms.txt").write_text("templates/flask\n", encoding="utf-8")
            fake_script = root / "scripts" / "check_docs_sync.py"

            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                self.assertEqual(check_docs_sync.main(), 0)

            self.assertIn("WARN: examples without smoke coverage", out.getvalue())
            self.assertIn("templates/flask/02-missing", out.getvalue())
            self.assertNotIn("ERROR: examples missing", out.getvalue())


class AllowlistReasonTests(unittest.TestCase):
    """An allowlist entry must record a reason (issue #174)."""

    def _load(self, text: str) -> set[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docs-sync-allowlist.txt"
            path.write_text(text, encoding="utf-8")
            return load_allowlist(path)

    def test_entry_with_reason_is_accepted(self) -> None:
        self.assertEqual(
            self._load("performance/bulk-insert  # benchmark: non-deterministic timing\n"),
            {"performance/bulk-insert"},
        )

    def test_reason_may_contain_hash_characters(self) -> None:
        self.assertEqual(
            self._load("templates/ai-agent  # tested by #111's suite, see issue #150\n"),
            {"templates/ai-agent"},
        )

    def test_blank_lines_and_comment_lines_are_ignored(self) -> None:
        text = "# header\n\n   \n  # indented comment\nperformance/foo  # reason\n"
        self.assertEqual(self._load(text), {"performance/foo"})

    def test_entry_without_reason_names_the_line(self) -> None:
        text = "# header\n\nperformance/ok  # reason\nperformance/foo\n"
        with self.assertRaises(ValueError) as ctx:
            self._load(text)
        message = str(ctx.exception)
        self.assertIn("docs-sync-allowlist.txt:4", message)
        self.assertIn("performance/foo", message)

    def test_entry_with_empty_reason_is_rejected(self) -> None:
        for text in ("performance/foo  #\n", "performance/foo  #   \n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self._load(text)

    def test_missing_allowlist_is_empty(self) -> None:
        self.assertEqual(load_allowlist(Path("/does/not/exist.txt")), set())

    def test_malformed_allowlist_makes_main_exit_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / "scripts").mkdir()
            (repo_root / "scripts" / "docs-sync-allowlist.txt").write_text("performance/foo\n")
            (repo_root / "README.md").write_text("")
            (repo_root / "llms.txt").write_text("")
            fake_script = repo_root / "scripts" / "check_docs_sync.py"
            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                self.assertEqual(check_docs_sync.main(), 1)
            self.assertIn("docs-sync-allowlist.txt:1", out.getvalue())

    def test_repository_allowlist_is_valid(self) -> None:
        load_allowlist(ROOT / "scripts" / "docs-sync-allowlist.txt")


class FindUntestedTests(unittest.TestCase):
    """Exercise find_untested() and main()'s warning block (issue #455)."""

    def test_bare_example_is_untested_while_expected_and_nested_tests_are_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "bare").mkdir(parents=True)
            (root / "templates" / "golden" / "expected").mkdir(parents=True)
            (root / "templates" / "suite" / "sub" / "tests").mkdir(parents=True)

            examples = ["templates/bare", "templates/golden", "templates/suite"]
            untested = find_untested(root, examples, set())

            self.assertEqual(untested, ["templates/bare"])

    def test_regular_file_named_tests_or_expected_does_not_count_as_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "golden").mkdir(parents=True)
            (root / "templates" / "suite" / "sub").mkdir(parents=True)
            (root / "templates" / "golden" / "expected").write_text("Expected!")
            (root / "templates" / "suite" / "sub" / "tests").write_text("Tests!")

            examples = ["templates/golden", "templates/suite"]
            untested = find_untested(root, examples, set())

            self.assertEqual(untested, ["templates/golden", "templates/suite"])

    def test_allowlisted_example_is_not_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "allowed").mkdir(parents=True)

            examples = ["templates/allowed"]
            untested = find_untested(root, examples, {"templates/allowed"})

            self.assertEqual(untested, [])

    def test_main_warns_about_untested_examples_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "bare").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "README.md").write_text("templates/bare\n", encoding="utf-8")
            (root / "llms.txt").write_text("templates/bare\n", encoding="utf-8")
            fake_script = root / "scripts" / "check_docs_sync.py"

            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                exit_code = check_docs_sync.main()

                self.assertEqual(exit_code, 0)
                self.assertIn("WARN: examples without smoke coverage", out.getvalue())
                self.assertIn("templates/bare", out.getvalue())


class MainErrorTests(unittest.TestCase):
    """Exercise main()'s exit-1 error blocks on undocumented examples (issue
    #512)."""

    def test_example_missing_only_from_readme_makes_main_exit_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "bare" / "expected").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "README.md").write_text("")
            (root / "llms.txt").write_text("templates/bare\n")
            fake_script = root / "scripts" / "check_docs_sync.py"

            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                exit_code = check_docs_sync.main()

                self.assertEqual(exit_code, 1)
                self.assertIn("ERROR: examples missing from README.md:", out.getvalue())
                self.assertIn("templates/bare", out.getvalue())
                self.assertNotIn("ERROR: examples missing from llms.txt:", out.getvalue())
                self.assertNotIn("OK:", out.getvalue())

    def test_example_missing_only_from_llms_txt_makes_main_exit_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "bare" / "expected").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "README.md").write_text("templates/bare\n")
            (root / "llms.txt").write_text("")
            fake_script = root / "scripts" / "check_docs_sync.py"

            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                exit_code = check_docs_sync.main()

                self.assertEqual(exit_code, 1)
                self.assertIn("ERROR: examples missing from llms.txt:", out.getvalue())
                self.assertIn("templates/bare", out.getvalue())
                self.assertNotIn("ERROR: examples missing from README.md:", out.getvalue())
                self.assertNotIn("OK:", out.getvalue())

    def test_example_missing_from_both_files_prints_both_errors_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "templates" / "bare" / "expected").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "README.md").write_text("")
            (root / "llms.txt").write_text("")
            fake_script = root / "scripts" / "check_docs_sync.py"

            with (
                mock.patch.object(check_docs_sync, "__file__", str(fake_script)),
                mock.patch("sys.stdout", new_callable=io.StringIO) as out,
            ):
                exit_code = check_docs_sync.main()

                self.assertEqual(exit_code, 1)
                self.assertIn("ERROR: examples missing from README.md:", out.getvalue())
                self.assertIn("ERROR: examples missing from llms.txt:", out.getvalue())
                self.assertIn("templates/bare", out.getvalue())
                self.assertNotIn("OK:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
