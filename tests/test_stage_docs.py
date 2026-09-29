"""Regression tests for scripts/stage_docs.py (#154).

Staging copies repository docs into docs/ for the MkDocs site. These tests pin
that it rewrites relative links so they survive the move, reports links to
missing repository paths, never modifies the sources, and that mkdocs.yml keeps
internal planning pages unpublished and unresolved links fatal under --strict.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.stage_docs import GITHUB_BASE, STAGE, rewrite_text, stage  # noqa: E402


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class RewriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "SUPPORT_MATRIX.md", "# Matrix\n")
        _write(self.root, "LICENSE", "MIT\n")
        _write(self.root, "pitfalls/README.md", "# Pitfalls\n")
        _write(self.root, "fundamentals/connect/01_connect.py", "print(1)\n")
        _write(self.root, "docs/README.ko.md", "# ko\n")
        _write(self.root, "docs/demo.gif", "GIF")
        _write(self.root, "docs/internal/PRD.md", "# PRD\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def rewrite(self, text: str, src: str = "README.md", dst: str = "docs/catalog.md"):
        return rewrite_text(text, src, dst, self.root)

    def test_link_to_staged_source_points_at_its_page(self) -> None:
        text, errors = self.rewrite("[m](SUPPORT_MATRIX.md#top) and [p](pitfalls/)\n")
        self.assertEqual(errors, [])
        self.assertEqual(text, "[m](support-matrix.md#top) and [p](pitfalls.md)\n")

    def test_link_from_nested_source_is_resolved_from_its_directory(self) -> None:
        text, errors = self.rewrite(
            "[m](../SUPPORT_MATRIX.md)\n", src="pitfalls/README.md", dst="docs/pitfalls.md"
        )
        self.assertEqual(errors, [])
        self.assertEqual(text, "[m](support-matrix.md)\n")

    def test_other_repository_paths_become_github_urls(self) -> None:
        text, errors = self.rewrite(
            "[![b](https://img.example/b.svg)](LICENSE)\n[c](fundamentals/connect/)\n"
        )
        self.assertEqual(errors, [])
        self.assertIn(f"[![b](https://img.example/b.svg)]({GITHUB_BASE}/blob/main/LICENSE)", text)
        self.assertIn(f"[c]({GITHUB_BASE}/tree/main/fundamentals/connect)", text)

    def test_internal_docs_are_linked_on_github_not_on_the_site(self) -> None:
        text, errors = self.rewrite("[prd](docs/internal/PRD.md)\n[ko](docs/README.ko.md)\n")
        self.assertEqual(errors, [])
        self.assertIn(f"[prd]({GITHUB_BASE}/blob/main/docs/internal/PRD.md)", text)
        self.assertIn("[ko](README.ko.md)", text)

    def test_raw_html_asset_accounts_for_directory_urls(self) -> None:
        text, errors = self.rewrite('<img src="docs/demo.gif" alt="d"/>\n')
        self.assertEqual(errors, [])
        self.assertEqual(text, '<img src="../demo.gif" alt="d"/>\n')

    def test_external_anchor_and_code_links_are_untouched(self) -> None:
        source = (
            "[x](https://example.com) [y](#local) `[z](LICENSE)`\n"
            "```markdown\n[w](missing.md)\n```\n"
        )
        text, errors = self.rewrite(source)
        self.assertEqual(errors, [])
        self.assertEqual(text, source)

    def test_missing_target_is_reported(self) -> None:
        _, errors = self.rewrite("[gone](templates/error-handling/)\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("templates/error-handling", errors[0])

    def test_stage_writes_pages_without_touching_sources(self) -> None:
        readme = _write(self.root, "README.md", "[m](SUPPORT_MATRIX.md)\n")
        before = readme.read_bytes()
        self.assertEqual(stage(self.root), [])
        self.assertEqual(readme.read_bytes(), before)
        staged = (self.root / "docs/catalog.md").read_text(encoding="utf-8")
        self.assertEqual(staged, "[m](support-matrix.md)\n")


class RepositoryDocsTests(unittest.TestCase):
    def test_every_staged_source_has_only_resolvable_links(self) -> None:
        for src, dst in STAGE:
            with self.subTest(src=src):
                text = (ROOT / src).read_text(encoding="utf-8")
                _, errors = rewrite_text(text, src, dst, ROOT)
                self.assertEqual(errors, [])

    def test_mkdocs_excludes_internal_docs_and_fails_on_broken_links(self) -> None:
        config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertRegex(config, r"exclude_docs: \|\n\s+internal/\n")
        for key in ("not_found", "unrecognized_links", "anchors"):
            self.assertRegex(config, rf"\n\s+{key}: warn\n")


if __name__ == "__main__":
    unittest.main()
