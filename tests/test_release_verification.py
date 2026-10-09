"""Release verification contract for upstream releases: request_id, run name and report."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
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
ALL_CELLS = (("11.2", "3.12"), ("11.4", "3.11"), ("11.4", "3.12"))
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
    "python",
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

    def run_matrix(self, event_name: str, cells=ALL_CELLS) -> None:
        """Simulate the smoke jobs: freeze the request, then write each job's part."""
        request = None
        with contextlib.suppress(ValueError):
            request = smoke.read_request(event_name, self.event)
        smoke.freeze(self.state, self.constraints, request)
        self.write_parts(event_name, cells)

    def write_parts(self, event_name: str, cells=ALL_CELLS) -> None:
        for cubrid, python in cells:
            directory = self.parts / f"release-verification-part-cubrid-{cubrid}-py{python}"
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
                    python,
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
        self.assertEqual([part["cubrid"] for part in report["matrix"]], ["11.2", "11.4", "11.4"])
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
        self.run_matrix("repository_dispatch", (("11.2", "3.12"),))
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
        # The default cells keep their documented artifact names; only the extra
        # Python cell gets a -py suffix so it cannot overwrite the 11.4 result.
        self.assertIn(
            "name: release-verification-part-cubrid-${{ matrix.cubrid }}"
            "${{ matrix.python != '3.12' && format('-py{0}', matrix.python) || '' }}",
            verify,
        )
        report = WORKFLOW[WORKFLOW.index("\n  report:") :]
        self.assertIn("needs: verify", report)
        self.assertIn("always() && (github.event_name == 'repository_dispatch'", report)
        self.assertIn("VERIFY_RESULT: ${{ needs.verify.result }}", report)
        self.assertIn("name: ${{ steps.report.outputs.artifact }}", report)
        self.assertIn("if-no-files-found: error", report)
        # Re-running failed jobs must be able to replace both artifacts.
        self.assertEqual(WORKFLOW.count("overwrite: true"), 2)
        self.assertNotIn("pypi", report.lower())

    def test_report_lists_a_python_311_cell_and_names_its_failure(self) -> None:
        self.payload(request_id="test-238-a1b2c3")
        self.run_matrix("repository_dispatch")
        passed, _ = self.report("repository_dispatch")
        self.assertTrue(passed)
        report = json.loads(self.output.read_text())
        self.assertEqual(
            [(part["cubrid"], part["python"]) for part in report["matrix"]],
            [("11.2", "3.12"), ("11.4", "3.11"), ("11.4", "3.12")],
        )
        # A failed 3.11 cell fails the release and says which cell it was.
        failed = self.parts / "release-verification-part-cubrid-11.4-py3.11" / smoke.REPORT_PART
        part = json.loads(failed.read_text())
        failed.write_text(json.dumps({**part, "result": "failure"}))
        passed, _ = self.report("repository_dispatch")
        self.assertFalse(passed)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["status"], "failure")
        self.assertEqual(
            report["reasons"],
            ["CUBRID 11.4, Python 3.11: verification passed, result failure"],
        )

    def test_release_verification_adds_only_a_python_311_cell(self) -> None:
        verify = WORKFLOW[WORKFLOW.index("\n  verify:") : WORKFLOW.index("\n  report:")]
        strategy = verify[verify.index("    strategy:") : verify.index("    steps:")]
        # Default cells: the two CUBRID versions on the current Python 3.12.
        self.assertIn('        cubrid: ["11.2", "11.4"]\n', strategy)
        self.assertIn('        python: ["3.12"]\n', strategy)
        # The one extra cell is CUBRID 11.4 on the supported minimum, 3.11 ...
        self.assertEqual(
            re.findall(r"\[\{[^]]*\}\]", strategy), ['[{"cubrid": "11.4", "python": "3.11"}]']
        )
        self.assertIn(
            '&& \'[{"cubrid": "11.4", "python": "3.11"}]\' || \'[]\'', " ".join(strategy.split())
        )
        # ... added only for a release verification, the concurrency group's condition.
        condition = "github.event_name == 'repository_dispatch' || (inputs.package && inputs.package != 'latest')"
        self.assertIn(condition, " ".join(strategy.split()))
        self.assertIn(condition, " ".join(WORKFLOW[WORKFLOW.index("concurrency:") :].split()))
        # Setup uses the cell's Python, with no stray hard-coded version left.
        self.assertIn("python-version: ${{ matrix.python }}", verify)
        self.assertNotIn(
            "python-version:", verify.replace("python-version: ${{ matrix.python }}", "")
        )
        self.assertIn('--python "$PYTHON_VERSION"', verify)
        self.assertIn("PYTHON_VERSION: ${{ matrix.python }}", verify)
        # The job name of the existing cells does not change; the extra cell is labelled.
        self.assertIn(
            "name: Smoke Tests (CUBRID ${{ matrix.cubrid }}"
            "${{ matrix.python != '3.12' && format(', Python {0}', matrix.python) || '' }})",
            verify,
        )
        # No new trigger or schedule: still the single daily cron.
        self.assertEqual(WORKFLOW.count("cron:"), 1)

    def test_summary_command_records_the_python_of_the_cell(self) -> None:
        self.payload(request_id="test-238-a1b2c3")
        request = smoke.read_request("repository_dispatch", self.event)
        smoke.freeze(self.state, self.constraints, request)
        self.parts.mkdir()
        part_file = self.parts / "part.json"
        argv = [
            "release_smoke.py",
            "summary",
            "--event-name",
            "repository_dispatch",
            "--event-path",
            str(self.event),
            "--state",
            str(self.state),
            "--commit",
            "abc",
            "--server",
            "11.4.0.0150",
            "--result",
            "success",
            "--part",
            str(part_file),
            "--cubrid",
            "11.4",
            "--python",
            "3.11",
        ]
        with (
            patch.object(smoke.sys, "argv", argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            smoke.main()
        part = json.loads(part_file.read_text())
        self.assertEqual((part["cubrid"], part["python"]), ("11.4", "3.11"))

    def test_report_matrix_is_sorted_by_cubrid_then_python(self) -> None:
        self.payload(request_id="test-238-a1b2c3")
        request = smoke.read_request("repository_dispatch", self.event)
        smoke.freeze(self.state, self.constraints, request)
        # Written in reverse order; "11.4"/"3.11" must still precede "11.4"/"3.12".
        self.write_parts("repository_dispatch", tuple(reversed(ALL_CELLS)))
        # Parts are read in path order, so name the directories to arrive out of order.
        for cell_dir, name in (("11.4-py3.12", "11.4-a"), ("11.4-py3.11", "11.4-b")):
            (self.parts / f"release-verification-part-cubrid-{cell_dir}").rename(
                self.parts / f"release-verification-part-cubrid-{name}"
            )
        passed, _ = self.report("repository_dispatch")
        self.assertTrue(passed)
        report = json.loads(self.output.read_text())
        self.assertEqual([(p["cubrid"], p["python"]) for p in report["matrix"]], list(ALL_CELLS))

    def test_release_requires_exactly_the_workflow_matrix_cells(self) -> None:
        verify = WORKFLOW[WORKFLOW.index("\n  verify:") : WORKFLOW.index("\n  report:")]
        strategy = verify[verify.index("    strategy:") : verify.index("    steps:")]
        cubrids = re.search(r"cubrid: \[(.*?)\]", strategy).group(1)
        pythons = re.search(r"python: \[(.*?)\]", strategy).group(1)
        cells = {
            (c, p)
            for c in re.findall(r'"([^"]+)"', cubrids)
            for p in re.findall(r'"([^"]+)"', pythons)
        }
        cells |= {
            (m[0], m[1])
            for m in re.findall(r'\{"cubrid": "([^"]+)", "python": "([^"]+)"\}', strategy)
        }
        self.assertEqual(cells, set(ALL_CELLS))
        self.assertEqual(smoke.RELEASE_CELLS, cells)

    def test_missing_or_duplicate_cells_fail_a_release_report(self) -> None:
        self.payload(request_id="test-238-a1b2c3")
        request = smoke.read_request("repository_dispatch", self.event)
        smoke.freeze(self.state, self.constraints, request)
        for missing in ALL_CELLS:
            with self.subTest(missing=missing):
                self.write_parts("repository_dispatch", tuple(c for c in ALL_CELLS if c != missing))
                passed, _ = self.report("repository_dispatch")
                self.assertFalse(passed)
                reasons = json.loads(self.output.read_text())["reasons"]
                self.assertEqual(len(reasons), 1, reasons)
                self.assertIn("no result reported", reasons[0])
                shutil.rmtree(self.parts)
        # The same cell reported twice (e.g. a re-run artifact under another name).
        self.write_parts("repository_dispatch", ALL_CELLS)
        copy = self.parts / "release-verification-part-cubrid-11.4-py3.11-copy"
        copy.mkdir()
        shutil.copy(
            self.parts / "release-verification-part-cubrid-11.4-py3.11" / smoke.REPORT_PART, copy
        )
        passed, _ = self.report("repository_dispatch")
        self.assertFalse(passed)
        reasons = json.loads(self.output.read_text())["reasons"]
        self.assertEqual(reasons, ["CUBRID 11.4, Python 3.11: reported 2 times"])

    def test_cell_names_omit_the_default_python(self) -> None:
        self.assertEqual(smoke.cell({"cubrid": "11.2", "python": "3.12"}), "CUBRID 11.2")
        self.assertEqual(
            smoke.cell({"cubrid": "11.4", "python": "3.11"}), "CUBRID 11.4, Python 3.11"
        )


if __name__ == "__main__":
    unittest.main()
