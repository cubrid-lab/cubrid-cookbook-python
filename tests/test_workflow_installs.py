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
CI = ROOT / ".github/workflows/ci.yml"

UV_ACTION = "astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7"
UV_VERSION = '"0.12.17"'
UV_JOBS = {"lint-python", "quickstart-tests", "docs-site", "pytest-suites"}
PIP_INSTALL = re.compile(r"(?<!uv )\bpip3?\s+install\b")


def uv_step(body: list[str]) -> list[str]:
    """Lines of the job's ``setup-uv`` step (up to the next step)."""
    start = next(i for i, line in enumerate(body) if UV_ACTION in line)
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
                self.assertEqual(text.count("astral-sh/setup-uv@"), 1)
                self.assertIn(f"uses: {UV_ACTION} # v10.2.0", text)
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
                    self.assertNotIn("astral-sh/setup-uv@", "\n".join(body))


if __name__ == "__main__":
    unittest.main()
