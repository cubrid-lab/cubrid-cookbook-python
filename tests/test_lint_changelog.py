"""Standard ``###`` release-note sections (AGENTS.md "GitHub Release Policy").

Runs the real ``scripts/lint_changelog.py`` CLI against independent fixtures.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALL_SECTIONS = (
    "Upgrade notes",
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Performance",
    "Documentation",
    "CI",
    "Tests",
)


class LintChangelogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        self.script = scripts / "lint_changelog.py"
        self.script.write_text((ROOT / "scripts/lint_changelog.py").read_text(encoding="utf-8"))

    def lint(self, changelog: str) -> subprocess.CompletedProcess[str]:
        (self.tmp / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(self.script)], capture_output=True, text=True, check=False
        )

    def assert_valid(self, changelog: str) -> None:
        result = self.lint(changelog)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_rejected(self, changelog: str, message: str) -> None:
        result = self.lint(changelog)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(message, result.stderr)

    @staticmethod
    def prefix(release: str) -> str:
        return "## [Unreleased]\n" if release != "Unreleased" else ""

    def test_repository_changelog_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/lint_changelog.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_standard_sections_in_order_are_valid(self) -> None:
        body = "".join(f"### {title}\n- Entry\n" for title in ALL_SECTIONS)
        for release in ("Unreleased", "0.2.1"):
            with self.subTest(release=release):
                self.assert_valid(
                    self.prefix(release) + f"## [{release}]\n{body}## [0.2.0]\n### Fixed\n- Old\n"
                )

    def test_nonstandard_section_is_rejected(self) -> None:
        for release in ("Unreleased", "0.2.1", "2.0.0"):
            for heading in ("Docs", "Release automation", "Bug Fixes"):
                with self.subTest(release=release, heading=heading):
                    self.assert_rejected(
                        self.prefix(release) + f"## [{release}]\n### {heading}\n- Entry\n",
                        f"Subsection '### {heading}' in [{release}] is not a standard section",
                    )

    def test_out_of_order_sections_are_rejected(self) -> None:
        for first, second in (
            ("Fixed", "Added"),
            ("Tests", "CI"),
            ("Documentation", "Upgrade notes"),
        ):
            with self.subTest(first=first, second=second):
                self.assert_rejected(
                    f"## [Unreleased]\n### {first}\n- A\n### {second}\n- B\n",
                    f"'### {second}' in [Unreleased] must come before '### {first}'",
                )

    def test_empty_section_is_rejected(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n### Added\n\n### Fixed\n- Entry\n",
            "Subsection '### Added' in [Unreleased] is empty",
        )

    def test_duplicate_section_is_rejected(self) -> None:
        for release in ("Unreleased", "0.2.1"):
            with self.subTest(release=release):
                self.assert_rejected(
                    self.prefix(release)
                    + f"## [{release}]\n### Fixed\n- First\n### Fixed\n- Second\n",
                    f"Duplicate subsection '### Fixed' in [{release}]",
                )

    def test_duplicate_section_with_other_spacing_is_rejected(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n### Fixed\n- First\n###  Fixed\n- Second\n",
            "Duplicate subsection '### Fixed' in [Unreleased]",
        )

    def test_cutoff_and_older_releases_keep_historical_sections(self) -> None:
        for release in ("0.2.0", "0.1.1", "0.1.0"):
            with self.subTest(release=release):
                self.assert_valid(
                    f"## [Unreleased]\n## [{release}]\n### Docs\n- A\n"
                    "### Fixed\n- C\n### Added\n- D\n### Release automation\n"
                )

    def test_unparsable_release_name_fails_safe(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n## [next]\n### Docs\n- A\n", "'### Docs' in [next] is not"
        )

    def test_fenced_lines_are_content_not_headings(self) -> None:
        self.assert_valid(
            "## [Unreleased]\n### Added\n```\n### Docs\n## [9.9.9]\n```\n### Fixed\n- Entry\n"
        )

    def test_fenced_version_does_not_split_the_release(self) -> None:
        # A fenced "## [9.9.9]" must not start a release, so the later "### Added"
        # repeats the first one in [Unreleased].
        result = self.lint(
            "## [Unreleased]\n### Added\n```\n## [9.9.9]\n### Added\n```\n### Added\n- x\n"
        )
        self.assertEqual(result.returncode, 1)

    def test_unclosed_code_fence_is_rejected(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n### Added\n```python\nx = 1\n### Docs\n- a\n### Fixed\n- b\n",
            "ERROR: Unclosed code fence in CHANGELOG.md",
        )

    def test_previous_releases_block_is_not_checked(self) -> None:
        self.assert_valid(
            "## [Unreleased]\n### Added\n- New\n### Previous Releases\n- Old\n"
            "### Changed\n- Old\n### Fixed\n- Old\n### Changed\n- Old again\n"
        )

    def test_previous_releases_block_ends_with_its_release(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n### Previous Releases\n- Old\n## [0.2.1]\n### Docs\n- A\n",
            "'### Docs' in [0.2.1] is not a standard section",
        )

    def test_headings_before_the_historical_block_are_still_checked(self) -> None:
        self.assert_rejected(
            "## [Unreleased]\n### Docs\n- A\n### Previous Releases\n- Old\n",
            "'### Docs' in [Unreleased] is not a standard section",
        )

    def test_same_section_across_releases_is_valid(self) -> None:
        # The order and duplicate checks restart for every release.
        self.assert_valid(
            "## [Unreleased]\n### Fixed\n- New\n## [0.2.2]\n### Fixed\n- Newer\n"
            "## [0.2.1]\n### Fixed\n- New\n## [0.2.0]\n### Fixed\n- Old\n"
        )

    def test_changelog_without_release_sections_is_rejected(self) -> None:
        self.assert_rejected("# Changelog\n### Added\n- x\n", "No version sections found")


if __name__ == "__main__":
    unittest.main()
