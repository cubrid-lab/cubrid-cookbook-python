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
    find_undocumented,
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


if __name__ == "__main__":
    unittest.main()
