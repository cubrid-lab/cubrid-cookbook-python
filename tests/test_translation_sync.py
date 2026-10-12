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
            ["git", "diff", "--name-only", "--no-renames", "origin/main...HEAD"],
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

    def test_blank_lines_are_dropped(self) -> None:
        files, _ = self._run("README.md\n\n  \nCHANGELOG.md\n", {"BASE_REF": "main"})
        self.assertEqual(files, {"README.md", "CHANGELOG.md"})


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class ChangedFilesRealGitTests(unittest.TestCase):
    """Run the real ``git diff`` so the tests use git's actual output format."""

    def _changed(self, mutate) -> set[str]:  # type: ignore[no-untyped-def]
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "-q", "-b", "main")
            body = "".join(f"line {i}\n" for i in range(40))
            (repo / "README.md").write_text(body, encoding="utf-8")
            (repo / "other.md").write_text("unrelated\n", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "base")
            _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
            mutate(repo, body)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "change")
            os.chdir(repo)
            try:
                with mock.patch.dict(os.environ, {"BASE_REF": "main"}):
                    return check_translation_sync.changed_files()
            finally:
                os.chdir(previous)

    def test_modification_lists_the_path(self) -> None:
        files = self._changed(lambda repo, body: (repo / "README.md").write_text(body + "x\n"))
        self.assertEqual(files, {"README.md"})

    def test_rename_lists_old_and_new_paths(self) -> None:
        files = self._changed(lambda repo, body: (repo / "README.md").rename(repo / "GUIDE.md"))
        self.assertEqual(files, {"README.md", "GUIDE.md"})

    def test_rename_with_edits_lists_old_and_new_paths(self) -> None:
        def mutate(repo: Path, body: str) -> None:
            (repo / "README.md").rename(repo / "GUIDE.md")
            (repo / "GUIDE.md").write_text(body + "edited\n", encoding="utf-8")

        self.assertEqual(self._changed(mutate), {"README.md", "GUIDE.md"})

    def test_copy_lists_only_the_new_path(self) -> None:
        # The source of a copy is unchanged, so only the new file is a change.
        files = self._changed(
            lambda repo, body: (repo / "COPY.md").write_text(body, encoding="utf-8")
        )
        self.assertEqual(files, {"COPY.md"})

    def test_rename_of_source_triggers_the_korean_requirement(self) -> None:
        files = self._changed(lambda repo, body: (repo / "README.md").rename(repo / "GUIDE.md"))
        self.assertIn(check_translation_sync.SOURCE.as_posix(), files)


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
