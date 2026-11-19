"""``ci.yml`` installs dependencies with a pinned uv, never bare pip (#229).

Resolution is unchanged from pip (same requirements files); uv only replaces the
installer. Kept on pip on purpose: the reusable ``live-smoke.yml`` ``setup-command``
inputs (they run in the organization's workflow, which does not provide uv), the
``driver-floors`` job and ``pr-smoke`` action (``make deps`` / ``scripts/driver_floors.py``
honour ``PIP_CONSTRAINT`` and pip's provenance output), ``smoke-test.yml`` (release
verification and candidate provenance read pip's ``direct_url.json``), ``driver-main.yml``
and ``docs.yml``.

Text-based on purpose: the offline suite does not install a YAML parser.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_workflow_timeouts import parse_jobs

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github/workflows"
CI = WORKFLOW_DIR / "ci.yml"

UV_ACTION_PREFIX = "astral-sh/setup-uv@"
UV_ACTION_REF = re.compile(rf"{re.escape(UV_ACTION_PREFIX)}([^\s#'\"]*)")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
# Dependabot rewrites the SHA and the version comment together; the test
# requires a pin with a version comment, not one version (#552).
UV_PIN = re.compile(r"uses: astral-sh/setup-uv@[0-9a-f]{40} # v\d+(?:\.\d+)*\b")
UV_VERSION = '"0.12.17"'
UV_JOBS = {"lint-python", "quickstart-tests", "docs-site", "docs-check", "pytest-suites"}
PIP_INSTALL = re.compile(r"(?<!uv )\bpip3?\s+install\b")


def uv_ref_problem(refs: set[str]) -> str | None:
    """Say what is wrong with the setup-uv refs, without naming the expected SHA (#552).

    Dependabot bumps the action in the workflows only, so the test checks what
    the pin is for: one ref everywhere, and a full commit SHA.
    """
    if len(refs) != 1:
        return f"setup-uv must use one ref everywhere, found {sorted(refs)}"
    ref = next(iter(refs))
    if not FULL_SHA.fullmatch(ref):
        return f"setup-uv must be pinned to a full commit SHA, found {ref!r}"
    return None


def workflow_uv_refs() -> set[str]:
    return {
        ref
        for path in WORKFLOW_DIR.glob("*.yml")
        for ref in UV_ACTION_REF.findall(path.read_text(encoding="utf-8"))
    }


def uv_step(body: list[str]) -> list[str]:
    """Lines of the job's ``setup-uv`` step (up to the next step)."""
    start = next(i for i, line in enumerate(body) if UV_ACTION_PREFIX in line)
    end = next(
        (i for i in range(start + 1, len(body)) if body[i].startswith("      - ")), len(body)
    )
    return body[start:end]


class WorkflowInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = parse_jobs(CI.read_text())

    def test_uv_jobs_set_up_pinned_uv_after_python_with_a_per_job_cache(self) -> None:
        for name in sorted(UV_JOBS):
            body = self.jobs[name]
            text = "\n".join(body)
            with self.subTest(job=name):
                self.assertEqual(text.count(UV_ACTION_PREFIX), 1)
                self.assertRegex(text, UV_PIN)
                step = "\n".join(uv_step(body))
                self.assertIn(f"version: {UV_VERSION}", step)
                self.assertIn("enable-cache: true", step)
                self.assertIn("cache-suffix: ${{ github.job }}", step)
                self.assertRegex(step, r'cache-dependency-glob: "[^"]+"')
                # The cache key carries the job's Python spec, not a drifting patch.
                self.assertIn('python-version: "3.12"', step)
                self.assertLess(
                    text.index("actions/setup-python@"), text.index("astral-sh/setup-uv@")
                )

    def test_setup_uv_has_one_full_sha_pin(self) -> None:
        self.assertIsNone(uv_ref_problem(workflow_uv_refs()))

    def test_a_new_setup_uv_sha_needs_no_test_edit(self) -> None:
        for refs in ({"a" * 40}, {"0123456789abcdef0123456789abcdef01234567"}):
            with self.subTest(refs=refs):
                self.assertIsNone(uv_ref_problem(refs))

    def test_setup_uv_ref_problems_are_reported(self) -> None:
        for refs, message in (
            ({"a" * 40, "b" * 40}, "one ref"),
            ({"a" * 40, ""}, "one ref"),
            ({""}, "full commit SHA"),
            ({"v10.3.3"}, "full commit SHA"),
            ({"v10"}, "full commit SHA"),
            ({"main"}, "full commit SHA"),
            ({"68559e9"}, "full commit SHA"),
            ({"a" * 39}, "full commit SHA"),
            ({"a" * 41}, "full commit SHA"),
            ({"A" * 40}, "full commit SHA"),
            (set(), "one ref"),
        ):
            with self.subTest(refs=refs):
                problem = uv_ref_problem(refs)
                self.assertIsNotNone(problem)
                self.assertIn(message, problem or "")

    def test_workflow_uv_ref_is_read_without_its_comment_or_quotes(self) -> None:
        for line, ref in (
            ("      - uses: astral-sh/setup-uv@abc123 # v10.3.3\n", "abc123"),
            ("      - uses: 'astral-sh/setup-uv@abc123'\n", "abc123"),
            ('      - uses: "astral-sh/setup-uv@v10"\n', "v10"),
            ("      - uses: astral-sh/setup-uv@\n", ""),
        ):
            with self.subTest(line=line):
                self.assertEqual(UV_ACTION_REF.findall(line), [ref])

    def test_a_bumped_pin_keeps_its_version_comment(self) -> None:
        pin = "      - uses: astral-sh/setup-uv@" + "b" * 40
        for comment in (" # v10.4.0", " # v11.0", " # v11"):
            with self.subTest(comment=comment):
                self.assertRegex(pin + comment, UV_PIN)
        for comment in ("", " # main", " # 10.4.0"):
            with self.subTest(comment=comment):
                self.assertNotRegex(pin + comment, UV_PIN)

    def test_uv_jobs_install_with_uv_and_log_versions(self) -> None:
        for name in sorted(UV_JOBS):
            lines = [line.strip() for line in self.jobs[name]]
            with self.subTest(job=name):
                if name == "pytest-suites":
                    # Fresh venv per suite, installed with uv; no pip anywhere.
                    self.assertTrue(any(line.startswith('uv venv "$venv"') for line in lines))
                    self.assertTrue(
                        any(line.startswith("uv pip install -q --python") for line in lines)
                    )
                else:
                    self.assertTrue(
                        any(line.startswith("uv pip install --system ") for line in lines)
                    )
                    self.assertIn("uv pip freeze --system", lines)
                for line in lines:
                    if line.startswith("#"):
                        continue
                    self.assertNotRegex(line, PIP_INSTALL)
                    self.assertNotIn("-m venv", line)

    def test_pytest_suites_keep_one_fresh_venv_per_suite(self) -> None:
        text = "\n".join(self.jobs["pytest-suites"])
        self.assertIn('venv="$RUNNER_TEMP/suite-$index"', text)
        self.assertEqual(text.count("uv venv "), 2)  # the readiness probe and each suite
        self.assertIn('"$venv/bin/python" -m pytest', text)

    def test_other_jobs_do_not_gain_uv(self) -> None:
        for name, body in self.jobs.items():
            if name not in UV_JOBS:
                with self.subTest(job=name):
                    self.assertNotIn(UV_ACTION_PREFIX, "\n".join(body))


if __name__ == "__main__":
    unittest.main()
