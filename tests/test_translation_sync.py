"""Unit tests for scripts/check_translation_sync.py.

The gate fails a PR that changes README.md without the required Korean
translation, only warns for the community translations, and honors a
``BASE_REF`` that may or may not already carry an ``origin/`` prefix.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_translation_sync  # noqa: E402


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class ChangedFilesTests(unittest.TestCase):
    def _run(self, stdout: str, env: dict[str, str]) -> tuple[set[str], list[str]]:
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch("subprocess.run", return_value=_completed(stdout)) as run,
        ):
            files = check_translation_sync.changed_files()
        return files, run.call_args.args[0]

    def test_base_ref_defaults_to_origin_main(self) -> None:
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("BASE_REF", None)
            with mock.patch("subprocess.run", return_value=_completed("")) as run:
                check_translation_sync.changed_files()
        self.assertEqual(
            run.call_args.args[0],
            ["git", "diff", "--name-only", "--find-renames", "origin/main...HEAD"],
        )

    def test_base_ref_gets_origin_prefix(self) -> None:
        _, command = self._run("", {"BASE_REF": "release"})
        self.assertEqual(command[-1], "origin/release...HEAD")

    def test_base_ref_with_origin_prefix_is_kept(self) -> None:
        _, command = self._run("", {"BASE_REF": "origin/release"})
        self.assertEqual(command[-1], "origin/release...HEAD")

    def test_git_failure_is_raised(self) -> None:
        error = subprocess.CalledProcessError(128, ["git", "diff"])
        with mock.patch("subprocess.run", side_effect=error) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                check_translation_sync.changed_files()
        self.assertTrue(run.call_args.kwargs["check"])

    def test_tab_separated_paths_are_both_collected_and_blank_lines_dropped(self) -> None:
        # Pins the parser's tolerance for ``old<TAB>new`` lines only. Plain
        # ``git diff --name-only`` prints just the new path of a rename.
        stdout = "README.md\ndocs/old.md\tdocs/new.md\n\n  \nCHANGELOG.md\n"
        files, _ = self._run(stdout, {"BASE_REF": "main"})
        self.assertEqual(files, {"README.md", "docs/old.md", "docs/new.md", "CHANGELOG.md"})


class MainTests(unittest.TestCase):
    def _main(self, present: list[str], changed: set[str]) -> tuple[int, str]:
        """Run main() in a scratch repo that has docs/README.<lang>.md for ``present``."""
        out = io.StringIO()
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            for lang in present:
                (docs / f"README.{lang}.md").write_text("# translation\n", encoding="utf-8")
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(
                        check_translation_sync, "changed_files", return_value=changed
                    ),
                    contextlib.redirect_stdout(out),
                ):
                    code = check_translation_sync.main()
            finally:
                os.chdir(previous)
        return code, out.getvalue()

    def test_no_translations_present_passes(self) -> None:
        code, output = self._main([], {"README.md"})
        self.assertEqual(code, 0)
        self.assertIn("nothing to sync", output)

    def test_unchanged_readme_passes(self) -> None:
        code, output = self._main(["ko", "de"], {"CHANGELOG.md"})
        self.assertEqual(code, 0)
        self.assertIn("README.md unchanged", output)

    def test_readme_changed_without_korean_fails(self) -> None:
        code, output = self._main(["ko"], {"README.md"})
        self.assertEqual(code, 1)
        self.assertIn("::error::", output)
        self.assertIn("docs/README.ko.md (한국어)", output)
        self.assertIn("translations-deferred", output)

    def test_readme_changed_with_korean_passes(self) -> None:
        code, output = self._main(["ko"], {"README.md", "docs/README.ko.md"})
        self.assertEqual(code, 0)
        self.assertIn("translation sync OK", output)
        self.assertNotIn("::error::", output)

    def test_missing_community_translation_only_warns(self) -> None:
        code, output = self._main(
            ["ko", "de", "zh"], {"README.md", "docs/README.ko.md", "docs/README.de.md"}
        )
        self.assertEqual(code, 0)
        self.assertIn("::warning file=README.md::community translation drifted", output)
        self.assertIn("docs/README.zh.md (中文)", output)
        self.assertNotIn("docs/README.de.md (Deutsch)", output)
        self.assertNotIn("::error::", output)

    def test_missing_korean_fails_even_when_others_are_updated(self) -> None:
        code, output = self._main(["ko", "de"], {"README.md", "docs/README.de.md"})
        self.assertEqual(code, 1)
        self.assertIn("docs/README.ko.md (한국어)", output)
        self.assertNotIn("::warning", output)

    def test_unknown_language_is_labelled_by_its_code(self) -> None:
        code, output = self._main(["ko", "fr"], {"README.md", "docs/README.ko.md"})
        self.assertEqual(code, 0)
        self.assertIn("docs/README.fr.md (fr)", output)


if __name__ == "__main__":
    unittest.main()
