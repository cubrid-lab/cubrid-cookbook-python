"""Release verification contract for upstream releases: request_id, run name and report."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_verification", ROOT / "scripts/release_smoke.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
WORKFLOW = (ROOT / ".github/workflows/smoke-test.yml").read_text()
RUN = {"id": "42", "attempt": "1", "url": "https://example.test/runs/42", "commit": "abc"}
REPORT_KEYS = {
    "schema_version",
    "request_id",
    "package",
    "requested_version",
    "installed_version",
    "status",
    "reasons",
    "run",
    "matrix",
}
PART_KEYS = {
    "cubrid",
    "request_valid",
    "installed_version",
    "origin",
    "server",
    "verification",
    "result",
}


def render_run_name(event_name: str, payload: dict, inputs: dict) -> str:
    """Evaluate the workflow's run-name expression for the fields it uses."""
    header = WORKFLOW[: WORKFLOW.index("\non:")]
    expression = " ".join(header[header.index("run-name:") :].split())
    template = re.search(r"format\('([^']*)'", expression)
    assert template is not None, expression
    release = event_name == "repository_dispatch" or (
        event_name == "workflow_dispatch" and inputs.get("package") != "latest"
    )
    if not release:
        return " "
    values = (
        payload.get("package") or inputs.get("package"),
        payload.get("ref") or inputs.get("version"),
        payload.get("request_id") or inputs.get("request_id") or "none",
    )
    return template.group(1).format(*values)


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.event = self.root / "event.json"
        self.state = self.root / "state.json"
        self.constraints = self.root / "constraints.txt"
        self.parts = self.root / "parts"
        self.output = self.root / "report" / "release-verification.json"
        self.github_output = self.root / "github-output"
        self.versions = {
            "pycubrid": "1.8.0",
            "sqlalchemy-cubrid": "1.8.0",
            "cubrid-mcp-server": "0.4.0",
        }
        distribution = patch.object(smoke.metadata, "distribution", self.distribution)
        distribution.start()
        self.addCleanup(distribution.stop)

    def distribution(self, name: str) -> SimpleNamespace:
        if name not in self.versions:
            raise smoke.metadata.PackageNotFoundError(name)
        return SimpleNamespace(version=self.versions[name], read_text=lambda _: None)

    def payload(self, **fields: object) -> None:
        payload = {"package": "pycubrid", "ref": "v1.8.0", **fields}
        self.event.write_text(json.dumps({"client_payload": payload}))

    def manual(self, **fields: object) -> None:
        inputs = {"package": "pycubrid", "version": "1.8.0", **fields}
        self.event.write_text(json.dumps({"inputs": inputs}))

    def run_matrix(self, event_name: str, cubrids=("11.2", "11.4")) -> None:
        """Simulate the smoke jobs: freeze the request, then write each job's part."""
        request = None
        with contextlib.suppress(ValueError):
            request = smoke.read_request(event_name, self.event)
        smoke.freeze(self.state, self.constraints, request)
        self.write_parts(event_name, cubrids)

    def write_parts(self, event_name: str, cubrids=("11.2", "11.4")) -> None:
        for cubrid in cubrids:
            directory = self.parts / f"release-verification-part-cubrid-{cubrid}"
            directory.mkdir(parents=True, exist_ok=True)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(ValueError):
                smoke.summary(
                    event_name,
                    self.event,
                    self.state,
                    "abc",
                    "11.4.0.0150",
                    "success",
                    directory / smoke.REPORT_PART,
                    cubrid,
                )

    def report(self, event_name: str, verify_result: str = "success") -> tuple[bool, str]:
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            passed = smoke.report_releases(
                event_name,
                self.event,
                self.parts,
                verify_result,
                self.output,
                RUN,
                self.github_output,
            )
        return passed, text.getvalue()

    def outputs(self) -> dict[str, str]:
        lines = self.github_output.read_text().splitlines()
        return dict(line.split("=", 1) for line in lines)

    def test_valid_request_id_is_read_from_payload_and_manual_inputs(self) -> None:
        for request_id in ("test-187-a1b2c3", "a" * 8, "A" * 80, "pycubrid-1.8.0_run.7"):
            with self.subTest(request_id=request_id):
                self.payload(request_id=request_id)
                request = smoke.read_request("repository_dispatch", self.event)
                self.assertEqual(request["request_id"], request_id)
                self.manual(request_id=request_id)
                request = smoke.read_request("workflow_dispatch", self.event)
                self.assertEqual(request["request_id"], request_id)

    def test_missing_request_id_keeps_older_senders_working(self) -> None:
        for fields in ({}, {"request_id": None}, {"request_id": ""}):
            with self.subTest(fields=fields):
                self.payload(**fields)
                self.assertIsNone(
                    smoke.read_request("repository_dispatch", self.event)["request_id"]
                )
                self.manual(**fields)
                self.assertIsNone(smoke.read_request("workflow_dispatch", self.event)["request_id"])

    def test_invalid_request_id_fails_before_any_install(self) -> None:
        invalid = [
            "short",
            "a" * 7,
            "a" * 81,
            "has space1",
            "semi;colon",
            "$(echo hi)",
            "slash/id-123",
            "newline-id\n",
            "brack]et-12",
            "unicode-é-12",
            12345678,
            ["test-187-a1b2c3"],
            {"id": "test-187-a1b2c3"},
        ]
        for request_id in invalid:
            for event_name, write in (
                ("repository_dispatch", self.payload),
                ("workflow_dispatch", self.manual),
            ):
                with self.subTest(event=event_name, request_id=request_id):
                    write(request_id=request_id)
                    with (
                        patch.object(smoke.subprocess, "run") as install,
                        patch.object(smoke.subprocess, "check_call") as bootstrap,
                        patch.object(smoke.time, "sleep") as sleep,
                    ):
                        with self.assertRaisesRegex(ValueError, "request_id"):
                            smoke.select_releases(event_name, self.event, self.constraints)
                    install.assert_not_called()
                    bootstrap.assert_not_called()
                    sleep.assert_not_called()

    def test_manual_request_id_requires_a_pinned_package(self) -> None:
        self.event.write_text(
            json.dumps({"inputs": {"package": "latest", "version": "", "request_id": "abcdefgh"}})
        )
        with self.assertRaisesRegex(ValueError, "requires a non-latest package"):
            smoke.read_request("workflow_dispatch", self.event)

    def test_run_name_carries_request_id_package_and_version(self) -> None:
        dispatch = render_run_name(
            "repository_dispatch",
            {"package": "pycubrid", "ref": "v1.8.0", "request_id": "pycubrid-v1.8.0-123-1"},
            {},
        )
        self.assertEqual(
            dispatch, "Release verification pycubrid@v1.8.0 [request_id=pycubrid-v1.8.0-123-1]"
        )
        manual = render_run_name(
            "workflow_dispatch",
            {},
            {"package": "sqlalchemy-cubrid", "version": "1.8.0", "request_id": "test-187-x1"},
        )
        self.assertEqual(
            manual, "Release verification sqlalchemy-cubrid@1.8.0 [request_id=test-187-x1]"
        )
        # The bracketed token lets upstream match exactly, not by prefix.
        self.assertNotIn("[request_id=pycubrid-v1.8.0-123]", dispatch)
        legacy = render_run_name(
            "repository_dispatch", {"package": "pycubrid", "ref": "v1.8.0"}, {}
        )
        self.assertTrue(legacy.endswith("[request_id=none]"))
        # Whitespace-only run-name keeps GitHub's default title for other runs.
        self.assertEqual(render_run_name("workflow_dispatch", {}, {"package": "latest"}), " ")
        self.assertEqual(render_run_name("push", {}, {}), " ")
        header = " ".join(WORKFLOW[: WORKFLOW.index("\non:")].split())
        self.assertIn("|| ' ' }}", header)

    def test_report_json_schema_for_a_passing_release(self) -> None:
        self.payload(request_id="test-187-a1b2c3")
        self.run_matrix("repository_dispatch")
        passed, text = self.report("repository_dispatch")
        self.assertTrue(passed)
        report = json.loads(self.output.read_text())
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["request_id"], "test-187-a1b2c3")
        self.assertEqual(report["package"], "pycubrid")
        self.assertEqual(report["requested_version"], "1.8.0")
        self.assertEqual(report["installed_version"], "1.8.0")
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["reasons"], [])
        self.assertEqual(report["run"], RUN)
        self.assertEqual([part["cubrid"] for part in report["matrix"]], ["11.2", "11.4"])
        for part in report["matrix"]:
            self.assertEqual(set(part), PART_KEYS)
            self.assertEqual(part["installed_version"], "1.8.0")
            self.assertEqual(part["origin"], "package index")
            self.assertEqual(part["verification"], "passed")
        self.assertIn("| request_id | test-187-a1b2c3 |", text)
        self.assertIn("| installed_version | 1.8.0 |", text)
        self.assertIn("| status | success |", text)
        self.assertEqual(
            self.outputs(),
            {
                "release": "true",
                "artifact": "release-verification-test-187-a1b2c3",
                "status": "success",
                "request_id": "test-187-a1b2c3",
                "package": "pycubrid",
                "requested_version": "1.8.0",
                "installed_version": "1.8.0",
            },
        )

    def test_installed_version_mismatch_fails_the_report(self) -> None:
        self.manual(request_id="test-187-a1b2c3")
        self.run_matrix("workflow_dispatch")
        # A drifted install after freezing: every job reports what is really installed.
        parts = sorted(self.parts.glob(f"**/{smoke.REPORT_PART}"))
        drifted = json.loads(parts[0].read_text())
        drifted["installed_version"] = "1.7.1"
        parts[0].write_text(json.dumps(drifted))
        passed, text = self.report("workflow_dispatch")
        self.assertFalse(passed)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["status"], "failure")
        self.assertIsNone(report["installed_version"])
        self.assertIn("installed 1.7.1 differs from requested 1.8.0", " ".join(report["reasons"]))
        self.assertIn("| status | failure |", text)
        self.assertEqual(self.outputs()["status"], "failure")

    def test_mismatch_in_every_job_reports_the_wrong_version(self) -> None:
        self.payload(request_id="test-187-a1b2c3")
        self.run_matrix("repository_dispatch")
        # Later installs replaced the pinned release in every job.
        self.versions["pycubrid"] = "1.7.1"
        self.write_parts("repository_dispatch")
        passed, _ = self.report("repository_dispatch", "failure")
        report = json.loads(self.output.read_text())
        self.assertFalse(passed)
        self.assertEqual(report["installed_version"], "1.7.1")
        self.assertEqual({p["verification"] for p in report["matrix"]}, {"failed"})

    def test_missing_or_failed_jobs_fail_the_report(self) -> None:
        self.payload(request_id="test-187-a1b2c3")
        passed, _ = self.report("repository_dispatch")
        self.assertFalse(passed)
        self.assertIn(
            "no smoke job reported a result", json.loads(self.output.read_text())["reasons"]
        )
        self.run_matrix("repository_dispatch")
        for verify_result in ("failure", "cancelled", "skipped", ""):
            with self.subTest(verify_result=verify_result):
                passed, _ = self.report("repository_dispatch", verify_result)
                self.assertFalse(passed)

    def test_invalid_request_reports_failure_under_run_id(self) -> None:
        self.payload(request_id="bad id")
        self.run_matrix("repository_dispatch")
        passed, _ = self.report("repository_dispatch")
        self.assertFalse(passed)
        report = json.loads(self.output.read_text())
        self.assertIsNone(report["request_id"])
        self.assertIn("invalid release request", report["reasons"][0])
        self.assertEqual(self.outputs()["artifact"], "release-verification-run-42")

    def test_release_without_request_id_is_still_reported(self) -> None:
        self.payload()
        self.run_matrix("repository_dispatch")
        passed, _ = self.report("repository_dispatch")
        self.assertTrue(passed)
        self.assertEqual(self.outputs()["artifact"], "release-verification-run-42")

    def test_latest_run_is_not_a_release_verification(self) -> None:
        self.event.write_text(json.dumps({"inputs": {"package": "latest", "version": ""}}))
        self.run_matrix("workflow_dispatch")
        self.assertEqual(list(self.parts.glob(f"**/{smoke.REPORT_PART}")), [])
        passed, text = self.report("workflow_dispatch")
        self.assertTrue(passed)
        self.assertIn("not a release verification", text)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.outputs(), {"release": "false"})

    def test_report_command_exits_nonzero_on_mismatch(self) -> None:
        self.payload(request_id="test-187-a1b2c3")
        self.run_matrix("repository_dispatch", ("11.2",))
        argv = [
            "release_smoke.py",
            "report",
            "--event-name",
            "repository_dispatch",
            "--event-path",
            str(self.event),
            "--parts",
            str(self.parts),
            "--verify-result",
            "failure",
            "--output",
            str(self.output),
            "--github-output",
            str(self.github_output),
        ]
        with (
            patch.object(smoke.sys, "argv", argv),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as exit_,
        ):
            smoke.main()
        self.assertEqual(exit_.exception.code, 1)
        self.assertEqual(json.loads(self.output.read_text())["status"], "failure")

    def test_workflow_publishes_one_report_per_release_request(self) -> None:
        self.assertIn("      request_id:\n", WORKFLOW[: WORKFLOW.index("concurrency:")])
        verify = WORKFLOW[WORKFLOW.index("\n  verify:") : WORKFLOW.index("\n  report:")]
        self.assertIn('--part "$RUNNER_TEMP/release-verification-part.json"', verify)
        self.assertIn("name: release-verification-part-cubrid-${{ matrix.cubrid }}", verify)
        report = WORKFLOW[WORKFLOW.index("\n  report:") :]
        self.assertIn("needs: verify", report)
        self.assertIn("always() && (github.event_name == 'repository_dispatch'", report)
        self.assertIn("VERIFY_RESULT: ${{ needs.verify.result }}", report)
        self.assertIn("name: ${{ steps.report.outputs.artifact }}", report)
        self.assertIn("if-no-files-found: error", report)
        # Re-running failed jobs must be able to replace both artifacts.
        self.assertEqual(WORKFLOW.count("overwrite: true"), 2)
        self.assertNotIn("pypi", report.lower())


if __name__ == "__main__":
    unittest.main()
