"""Unit tests for scripts/check_docs_sync.py's pitfalls handling (issue #182).

``pitfalls`` mixes a README-only landing page with example subdirectories
that ship real recipe code (``pitfalls/reserved-words/``, added in #181).
These tests pin the two behaviors #182 requires: a pitfalls example
subdirectory that contains code must be discovered and, if undocumented,
must fail the gate; a README-only pitfalls page (no code subdirectories)
must stay exempt and pass.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_docs_sync import discover_examples, find_undocumented  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
