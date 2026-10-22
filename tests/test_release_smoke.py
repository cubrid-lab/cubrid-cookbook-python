"""Offline guards against testing different drivers than the workflow reports."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_smoke", ROOT / "scripts/release_smoke.py")
assert SPEC is not None and SPEC.loader is not None
release_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_smoke)


class ReleaseSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "drivers.json"
        self.constraints = self.root / "constraints.txt"
        self.versions = {"pycubrid": "1.7.1", "sqlalchemy-cubrid": "1.7.1"}
        self.direct_url = None
        mock = patch.object(release_smoke.metadata, "distribution", self.distribution)
        mock.start()
        self.addCleanup(mock.stop)

    def distribution(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(version=self.versions[name], read_text=lambda _: self.direct_url)

    def test_freeze_and_verify_index_releases(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        self.assertEqual(
            self.constraints.read_text(), "pycubrid==1.7.1\nsqlalchemy-cubrid==1.7.1\n"
        )
        release_smoke.verify(self.state)

    def test_changed_driver_version_fails(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        self.versions["pycubrid"] = "1.8.0"
        with self.assertRaisesRegex(ValueError, "versions changed"):
            release_smoke.verify(self.state)

    def test_same_version_vcs_replacement_fails(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        self.direct_url = '{"url": "https://github.com/cubrid-lab/pycubrid", "vcs_info": {}}'
        with self.assertRaisesRegex(ValueError, "not a direct URL"):
            release_smoke.verify(self.state)

    def test_cannot_select_local_or_vcs_driver(self) -> None:
        self.direct_url = '{"url": "file:///tmp/local-driver", "dir_info": {"editable": true}}'
        with self.assertRaisesRegex(ValueError, "not a direct URL"):
            release_smoke.freeze(self.state, self.constraints)
        self.assertFalse(self.constraints.exists())

    def test_same_version_local_replacement_fails(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        self.direct_url = '{"url": "file:///tmp/local-driver", "dir_info": {}}'
        with self.assertRaisesRegex(ValueError, "not a direct URL"):
            release_smoke.verify(self.state)

    def test_missing_constraints_fail_before_example_install(self) -> None:
        with patch.object(release_smoke.subprocess, "check_call") as install:
            with self.assertRaisesRegex(ValueError, "Missing release constraints"):
                release_smoke.install_examples(self.root, self.constraints)
        install.assert_not_called()

    def test_examples_without_requirements_need_no_install(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        (self.root / "no-extra-dependencies" / "expected").mkdir(parents=True)
        with patch.object(release_smoke.subprocess, "check_call") as install:
            release_smoke.install_examples(self.root, self.constraints)
        install.assert_not_called()

    def test_every_example_install_uses_release_constraints(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        for directory in ("first", "nested/second", ".hidden/example"):
            example = self.root / directory
            (example / "expected").mkdir(parents=True)
            (example / "requirements.txt").touch()
        with patch.object(release_smoke.subprocess, "check_call") as install:
            release_smoke.install_examples(self.root, self.constraints)
        self.assertEqual(install.call_count, 2)
        for call in install.call_args_list:
            command = call.args[0]
            self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
            self.assertEqual(command[4:6], ["--constraint", str(self.constraints)])

    def test_incompatible_requirement_fails_pip_resolution_without_network(self) -> None:
        release_smoke.freeze(self.state, self.constraints)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--disable-pip-version-check",
                "--constraint",
                str(self.constraints),
                "pycubrid==9.9.9",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ResolutionImpossible", result.stderr)
        self.assertIn("pycubrid==1.7.1", result.stdout + result.stderr)

    def test_golden_requirements_do_not_override_drivers_with_urls(self) -> None:
        for expected in ROOT.glob("**/expected"):
            requirements = expected.parent / "requirements.txt"
            if requirements.is_file():
                for line in requirements.read_text().splitlines():
                    if line.strip().startswith(release_smoke.DRIVERS):
                        self.assertNotIn("@", line, str(requirements))
                        self.assertNotIn("git+", line, str(requirements))

    def test_workflow_constrains_all_later_installs_and_reports_last(self) -> None:
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text()
        freeze = workflow.index("name: Freeze selected driver releases")
        mcp = workflow.index("name: Install dependencies")
        deps = workflow.index("name: Install verification dependencies")
        report = workflow.index("name: Record tested versions")
        verify = workflow.index("name: Run make verify")
        self.assertLess(freeze, mcp)
        self.assertLess(mcp, deps)
        self.assertLess(deps, report)
        self.assertLess(report, verify)
        self.assertIn("PIP_CONSTRAINT=$RUNNER_TEMP/release-constraints.txt", workflow)
        self.assertIn('install-mcp --state "$RUNNER_TEMP/release-drivers.json"', workflow)
        # make deps honours PIP_CONSTRAINT: every example keeps the selected drivers.
        self.assertIn("run: make deps\n", workflow[deps:report])
        self.assertIn("set -o pipefail", workflow[report:verify])
        self.assertNotIn("pip install", workflow[report:])
        self.assertNotIn("make deps", workflow[report:])


if __name__ == "__main__":
    unittest.main()
