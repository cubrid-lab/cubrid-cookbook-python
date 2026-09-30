"""Offline checks for the PR-title workflow (.github/workflows/pr-title.yml).

The validator lives only inside the workflow (it runs without a checkout), so
these tests extract the embedded script and execute it with PR_TITLE set.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-title.yml"
BEGIN = "# BEGIN pr-title-validator"
END = "# END pr-title-validator"
TYPES = (
    "feat",
    "fix",
    "docs",
    "test",
    "perf",
    "refactor",
    "ci",
    "build",
    "chore",
    "style",
    "revert",
)

VALID = (
    "fix: preserve cursor state after END_TRAN",
    "feat(aio): add charset connection option",
    "refactor(compiler)!: drop legacy LIMIT rendering",
    "feat!: require Python 3.10",
    "chore(deps): bump ruff from 0.16.8 to 0.16.9",
    "chore(deps-dev): bump pytest from 8.0.0 to 8.1.0",
    "chore: release v1.8.0",
    "chore(release): unify release workflow and add RELEASING.md",
    "ci: pin remaining workflow actions to full commit SHAs",
    "docs: document JSON as_numeric() input limits",
    "fix: coerce catalog COUNT(*) in has_table()/has_index()",
    "fix(types): compile BINARY, VARBINARY and UUID to types CUBRID accepts",
    "feat: CUBRID Skills — domain knowledge resources",
    "revert: restore the previous escape-mode probe",
    "build: switch the sdist backend to hatchling",
    "style: apply ruff format",
    "perf: reuse the packet buffer in fetch",
    "test: model transactional DDL in the connection state machine",
)

INVALID = (
    "",
    "Fix: preserve cursor state",
    "fix:preserve cursor state",
    "fix:  preserve cursor state",
    "fix : preserve cursor state",
    "fix: preserve cursor state.",
    "fix: preserve cursor state ",
    "fix: ",
    "[Bug]: cursor state is lost",
    "[WIP] fix: preserve cursor state",
    "fix: WIP preserve cursor state",
    "feature: add charset option",
    "epic: official driver parity",
    "security: reject blank passwords",
    "ci+docs: SBOM on releases",
    "Track: refresh 06_lob CLOB goldens",
    "check_docs_sync: scan pitfalls/* example directories",
    "feat: add charset connection option (#86)",
    "fix: resolve #415 docs: align support policy",
    "fix(Compiler): render Boolean IS",
    "fix(compiler engine): render Boolean IS",
    "fix(): render Boolean IS",
    "fix: 커서 상태 보존",
    "Keep new issue metadata visible without requiring reporter label access",
)


def _validator() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(BEGIN)
    stop = text.index(END, start)
    line_start = text.rindex("\n", 0, start) + 1
    return textwrap.dedent(text[line_start:stop])


def _run(title: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PR_TITLE": title}
    return subprocess.run(
        [sys.executable, "-c", _validator()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class PrTitleValidatorTest(unittest.TestCase):
    def test_valid_titles_pass(self) -> None:
        for title in VALID:
            with self.subTest(title=title):
                result = _run(title)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("::error", result.stdout)

    def test_invalid_titles_fail_with_guidance(self) -> None:
        for title in INVALID:
            with self.subTest(title=title):
                result = _run(title)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("::error title=PR title::", result.stdout)
                self.assertIn("Allowed types: " + ", ".join(TYPES), result.stdout)

    def test_capitalized_description_only_warns(self) -> None:
        result = _run("docs: Korean site pages")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("::warning title=PR title::", result.stdout)

    def test_invalid_header_error_lists_all_title_forms(self) -> None:
        result = _run("improve cursor handling")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "'type: description', 'type(scope): description', "
            "'type!: description', or 'type(scope)!: description'",
            result.stdout,
        )

    def test_workflow_is_unprivileged_and_stable(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n    types: [opened, edited, reopened, synchronize]", text)
        self.assertNotRegex(text, r"(?m)^\s*pull_request_target:")
        self.assertIn("\npermissions: {}\n", text)
        self.assertNotIn("actions/checkout", text)
        self.assertIn("PR_TITLE: ${{ github.event.pull_request.title }}", text)
        self.assertRegex(text, r"\n    name: PR title\n")
        run_block = text.split("run: |", 1)[1]
        self.assertNotIn("${{", run_block)

    def test_type_list_matches_workflow(self) -> None:
        match = re.search(r"TYPES = \((.*?)\)", _validator(), re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(tuple(re.findall(r'"([a-z]+)"', match[1])), TYPES)


if __name__ == "__main__":
    unittest.main()
