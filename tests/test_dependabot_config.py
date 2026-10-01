"""Guards for .github/dependabot.yml and workflow action pins (#153).

Text-based on purpose: the offline suite does not install a YAML parser.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "dependabot.yml"
WORKFLOWS = ROOT / ".github" / "workflows"
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@(\S+)(?:\s+#\s*(\S+))?", re.M)


def _pip_directories(config: str) -> list[str]:
    block = config.split("package-ecosystem: pip", 1)[1]
    listing = block.split("directories:", 1)[1]
    dirs = []
    for line in listing.splitlines()[1:]:
        match = re.match(r'^\s+-\s+"([^"]+)"\s*$', line)
        if not match:
            break
        dirs.append(match.group(1))
    return dirs


def _matches(directory: str, pattern: str) -> bool:
    # Dependabot's `*` matches one path segment.
    parts, globs = directory.split("/"), pattern.split("/")
    return len(parts) == len(globs) and all(fnmatchcase(p, g) for p, g in zip(parts, globs))


def _requirement_dirs() -> list[str]:
    files = subprocess.check_output(
        ["git", "ls-files", "*requirements*.txt"], cwd=ROOT, text=True
    ).split()
    return sorted({"/" + str(Path(f).parent.as_posix()) for f in files})


class DependabotConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CONFIG.read_text(encoding="utf-8")

    def test_ecosystems_are_configured(self) -> None:
        self.assertRegex(self.config, r"(?m)^version: 2$")
        self.assertIn("package-ecosystem: github-actions", self.config)
        self.assertIn("package-ecosystem: pip", self.config)

    def test_every_recipe_requirements_file_is_covered(self) -> None:
        patterns = _pip_directories(self.config)
        self.assertTrue(patterns)
        for directory in _requirement_dirs():
            with self.subTest(directory=directory):
                self.assertTrue(
                    any(_matches(directory, p) for p in patterns),
                    f"{directory} is not covered by the pip `directories` globs",
                )

    def test_commit_prefix_yields_conventional_titles(self) -> None:
        prefixes = re.findall(r"prefix:\s*\"([^\"]*)\"", self.config)
        self.assertEqual(prefixes, ["chore(deps)", "chore(deps)"])

    def test_pip_updates_are_grouped_across_directories(self) -> None:
        pip = self.config.split("package-ecosystem: pip", 1)[1]
        self.assertIn("group-by: dependency-name", pip)

    def test_pip_versioning_strategy_preserves_recipe_floors(self) -> None:
        # Otherwise GitHub's default "auto" strategy can raise a recipe's
        # documented driver floor (SUPPORT_MATRIX.md) on a minor/patch bump.
        pip = self.config.split("package-ecosystem: pip", 1)[1]
        self.assertIn("versioning-strategy: increase-if-necessary", pip)


class WorkflowPinTests(unittest.TestCase):
    def test_actions_are_sha_pinned_and_aligned(self) -> None:
        pins: dict[str, set[tuple[str, str]]] = {}
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for action, ref, tag in USES_RE.findall(workflow.read_text(encoding="utf-8")):
                if action.startswith("./"):
                    continue
                with self.subTest(workflow=workflow.name, action=action):
                    self.assertRegex(ref, r"^[0-9a-f]{40}$", "pin actions by full commit SHA")
                if "/.github/workflows/" in action:
                    continue  # reusable workflows carry no version comment
                with self.subTest(workflow=workflow.name, action=action):
                    self.assertRegex(tag, r"^v\d", "keep the `# vX.Y.Z` comment Dependabot updates")
                pins.setdefault(action, set()).add((ref, tag))
        for action, refs in pins.items():
            with self.subTest(action=action):
                self.assertEqual(len(refs), 1, f"{action} is pinned to several versions: {refs}")


if __name__ == "__main__":
    unittest.main()
