"""Package release workflows call smoke-test.yml as a reusable workflow (workflow_call).

Under workflow_call the github context and GITHUB_EVENT_PATH belong to the caller,
so the request must come from the call inputs (RELEASE_INPUT_* variables) and the
jobs must check out this repository at the called workflow's own commit.
"""

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
    "release_workflow_call", ROOT / "scripts/release_smoke.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
WORKFLOW = (ROOT / ".github/workflows/smoke-test.yml").read_text()
HEADER = WORKFLOW[: WORKFLOW.index("\njobs:")]
JOBS = WORKFLOW[WORKFLOW.index("\njobs:") :]
CALL = HEADER[HEADER.index("\n  workflow_call:") : HEADER.index("\nconcurrency:")]
VERIFY = JOBS[: JOBS.index("\n  report:")]
REPORT = JOBS[JOBS.index("\n  report:") :]
RUN = {"id": "42", "attempt": "1", "url": "https://example.test/runs/42", "commit": "abc"}


def call_env(package="pycubrid", version="1.8.0", request_id="test-190-a1b2c3") -> dict:
    return {
        "RELEASE_INPUT_PACKAGE": package,
        "RELEASE_INPUT_VERSION": version,
        "RELEASE_INPUT_REQUEST_ID": request_id,
    }


def run_blocks(text: str) -> list[str]:
    """Return the body of every `run:` step (inline or block scalar)."""
    blocks = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)run: ?(.*)$", line)
        if match is None:
            continue
        indent, rest = len(match.group(1)), match.group(2)
        if rest not in ("|", ">", "|-", ">-"):
            blocks.append(rest)
            continue
        body = []
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        blocks.append("\n".join(body))
    return blocks


class WorkflowCallInputTests(unittest.TestCase):
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
        # No network: the PyPI publication wait has its own tests (test_release_pypi_wait.py).
        wait = patch.object(smoke, "wait_for_pypi")
        self.wait = wait.start()
        self.addCleanup(wait.stop)
        # The caller's own event: a release push, whose JSON has no request at all.
        self.event.write_text(json.dumps({"ref": "refs/tags/v1.8.0", "after": "0" * 40}))

    def distribution(self, name: str) -> SimpleNamespace:
        if name not in self.versions:
            raise smoke.metadata.PackageNotFoundError(name)
        return SimpleNamespace(version=self.versions[name], read_text=lambda _: None)

    def test_call_inputs_come_from_the_environment_not_the_callers_event(self) -> None:
        for package, version in self.versions.items():
            for spelled in (version, "v" + version):
                with self.subTest(package=package, version=spelled):
                    request = smoke.read_request(
                        "workflow_call", self.event, call_env(package, spelled)
                    )
                    self.assertEqual(
                        request,
                        {
                            "package": package,
                            "ref": "v" + version,
                            "version": version,
                            "request_id": "test-190-a1b2c3",
                        },
                    )

    def test_callers_dispatch_inputs_and_payload_are_ignored(self) -> None:
        # A caller triggered by workflow_dispatch or repository_dispatch has its own
        # inputs/client_payload in the event JSON; they must never select a release.
        self.event.write_text(
            json.dumps(
                {
                    "inputs": {"package": "cubrid-mcp-server", "version": "9.9.9"},
                    "client_payload": {"package": "sqlalchemy-cubrid", "ref": "v9.9.9"},
                }
            )
        )
        request = smoke.read_request("workflow_call", self.event, call_env())
        self.assertEqual((request["package"], request["version"]), ("pycubrid", "1.8.0"))
        # The event file is not needed at all under a call.
        request = smoke.read_request("workflow_call", None, call_env(request_id=""))
        self.assertEqual(request["request_id"], None)

    def test_own_runs_ignore_release_input_variables(self) -> None:
        # Workflow-level env also carries manual inputs; only a call reads them.
        with patch.dict(smoke.os.environ, call_env("cubrid-mcp-server", "0.4.0")):
            self.assertIsNone(smoke.read_request("push", self.event))
            self.event.write_text(
                json.dumps({"inputs": {"package": "pycubrid", "version": "v1.8.0"}})
            )
            request = smoke.read_request("workflow_dispatch", self.event)
        self.assertEqual(request["package"], "pycubrid")

    def test_invalid_call_inputs_fail_before_any_install(self) -> None:
        invalid = [
            call_env(package=""),
            call_env(package="latest"),
            call_env(package="pycubrid --help"),
            call_env(package="PyCUBRID"),
            call_env(version=""),
            call_env(version="1.8"),
            call_env(version="v01.8.0"),
            call_env(version="1.8.0; rm -rf /"),
            call_env(version="1.8.0rc1"),
            call_env(request_id="short"),
            call_env(request_id="has space-12345"),
            call_env(request_id="x" * 81),
            {},
        ]
        for environ in invalid:
            with self.subTest(environ=environ):
                with self.assertRaises(ValueError):
                    smoke.read_request("workflow_call", self.event, environ)
                with (
                    patch.dict(smoke.os.environ, environ, clear=True),
                    patch.object(smoke.subprocess, "run") as install,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                    patch.object(smoke.time, "sleep") as sleep,
                    self.assertRaises(ValueError),
                ):
                    smoke.select_releases("workflow_call", self.event, self.constraints)
                install.assert_not_called()
                bootstrap.assert_not_called()
                sleep.assert_not_called()

    def test_call_flag_switches_the_cli_event_name(self) -> None:
        """RELEASE_WORKFLOW_CALL=true makes every subcommand read the call inputs."""
        environ = {
            **call_env(),
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_EVENT_PATH": str(self.event),
        }
        for flag, expected in (("true", "workflow_call"), ("", "push")):
            with self.subTest(flag=flag):
                argv = ["release_smoke.py", "select", "--constraints", str(self.constraints)]
                with (
                    patch.dict(smoke.os.environ, {**environ, "RELEASE_WORKFLOW_CALL": flag}),
                    patch.object(smoke.sys, "argv", argv),
                    patch.object(smoke, "select_releases") as select,
                ):
                    smoke.main()
                self.assertEqual(select.call_args.args[0], expected)

    def test_call_selects_exact_release_with_bounded_retries(self) -> None:
        failure = smoke.subprocess.CalledProcessError(1, ["pip"])
        with (
            patch.dict(smoke.os.environ, call_env()),
            patch.object(smoke.subprocess, "run", side_effect=failure) as install,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            patch.object(smoke.time, "sleep"),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaisesRegex(ValueError, "unavailable after 6 attempts"),
        ):
            smoke.select_releases("workflow_call", self.event, self.constraints)
        # The path that failed on 2026-10-09: the call must wait for PyPI first (C4).
        self.wait.assert_called_once_with("pycubrid", "1.8.0")
        self.assertEqual(install.call_count, 6)
        command = install.call_args.args[0]
        self.assertIn("pycubrid==1.8.0", command)
        self.assertIn("https://pypi.org/simple", command)
        self.assertFalse(any("git+" in argument for argument in command))
        bootstrap.assert_not_called()  # Never falls back to the latest release.

        self.versions["pycubrid"] = "1.7.1"  # pip "succeeded" with the wrong release.
        with (
            patch.dict(smoke.os.environ, call_env()),
            patch.object(smoke.subprocess, "run"),
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            self.assertRaisesRegex(ValueError, "differs from requested release 1.8.0"),
        ):
            smoke.select_releases("workflow_call", self.event, self.constraints)
        bootstrap.assert_not_called()

    def test_call_report_publishes_outputs_and_cookbook_commit(self) -> None:
        with patch.dict(smoke.os.environ, call_env()):
            request = smoke.read_request("workflow_call", self.event)
            smoke.freeze(self.state, self.constraints, request)
            for cubrid, python in (("11.2", "3.12"), ("11.4", "3.12"), ("11.4", "3.11")):
                directory = self.parts / f"release-verification-part-cubrid-{cubrid}-py{python}"
                directory.mkdir(parents=True)
                text = io.StringIO()
                with contextlib.redirect_stdout(text):
                    smoke.summary(
                        "workflow_call",
                        self.event,
                        self.state,
                        "c" * 40,
                        "11.4.0.0150",
                        "success",
                        directory / smoke.REPORT_PART,
                        cubrid,
                        python,
                    )
                self.assertIn("release workflow call: pycubrid v1.8.0", text.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                passed = smoke.report_releases(
                    "workflow_call",
                    self.event,
                    self.parts,
                    "success",
                    self.output,
                    RUN,
                    self.github_output,
                )
        self.assertTrue(passed)
        outputs = dict(line.split("=", 1) for line in self.github_output.read_text().splitlines())
        self.assertEqual(outputs["status"], "success")
        self.assertEqual(outputs["requested_version"], "1.8.0")
        self.assertEqual(outputs["installed_version"], "1.8.0")
        self.assertEqual(outputs["artifact"], "release-verification-test-190-a1b2c3")

        # GITHUB_SHA is the caller's commit under a call; report the cookbook's.
        argv = [
            "release_smoke.py",
            "report",
            "--parts",
            str(self.parts),
            "--verify-result",
            "success",
            "--output",
            str(self.output),
            "--github-output",
            str(self.root / "cli-output"),
        ]
        environ = {
            **call_env(),
            "RELEASE_WORKFLOW_CALL": "true",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_SHA": "a" * 40,
            "COOKBOOK_COMMIT": "b" * 40,
        }
        with (
            patch.dict(smoke.os.environ, environ),
            patch.object(smoke.sys, "argv", argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            smoke.main()
        run = json.loads(self.output.read_text())["run"]
        self.assertEqual(run["commit"], "b" * 40)
        self.assertEqual(run["event"], "workflow_call")

    def test_version_mismatch_fails_the_call_report(self) -> None:
        with patch.dict(smoke.os.environ, call_env()):
            request = smoke.read_request("workflow_call", self.event)
            smoke.freeze(self.state, self.constraints, request)
            directory = self.parts / "release-verification-part-cubrid-11.4"
            directory.mkdir(parents=True)
            self.versions["pycubrid"] = "1.7.1"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(ValueError):
                smoke.summary(
                    "workflow_call",
                    self.event,
                    self.state,
                    "c" * 40,
                    "11.4",
                    "success",
                    directory / smoke.REPORT_PART,
                    "11.4",
                )
            with contextlib.redirect_stdout(io.StringIO()):
                passed = smoke.report_releases(
                    "workflow_call",
                    self.event,
                    self.parts,
                    "success",
                    self.output,
                    RUN,
                    self.github_output,
                )
        self.assertFalse(passed)
        outputs = dict(line.split("=", 1) for line in self.github_output.read_text().splitlines())
        self.assertEqual(outputs["status"], "failure")


class WorkflowCallStaticTests(unittest.TestCase):
    def test_call_inputs_and_outputs_are_declared(self) -> None:
        inputs = CALL[CALL.index("\n    inputs:") : CALL.index("\n    outputs:")]
        declared = dict(re.findall(r"^      (\w+):\n((?:^        .*\n?)+)", inputs, re.M))
        self.assertEqual(set(declared), {"package", "version", "request_id"})
        for name in ("package", "version"):
            self.assertIn("type: string", declared[name])
            self.assertIn("required: true", declared[name])
        self.assertIn('default: ""', declared["request_id"])
        self.assertNotIn("required: true", declared["request_id"])
        self.assertNotIn("secrets:", CALL)
        outputs = CALL[CALL.index("\n    outputs:") :]
        report_outputs = REPORT[REPORT.index("\n    outputs:") : REPORT.index("\n    steps:")]
        for name in ("status", "requested_version", "installed_version", "artifact"):
            self.assertIn(f"value: ${{{{ jobs.report.outputs.{name} }}}}", outputs)
            self.assertIn(f"{name}: ${{{{ steps.report.outputs.{name} }}}}", report_outputs)

    def test_dispatch_triggers_are_kept(self) -> None:
        triggers = HEADER[HEADER.index("\non:") : HEADER.index("\nconcurrency:")]
        for trigger in ("repository_dispatch:", "workflow_dispatch:", "workflow_call:"):
            self.assertIn(f"\n  {trigger}", triggers)
        self.assertIn("types: [upstream-released]", triggers)

    def test_inputs_reach_the_script_only_as_environment_data(self) -> None:
        env = HEADER[HEADER.index("\nenv:") :]
        for name in ("package", "version", "request_id"):
            variable = smoke.CALL_INPUTS[name]
            self.assertIn(f"  {variable}: ${{{{ inputs.{name} }}}}\n", env)
        for block in run_blocks(WORKFLOW):
            self.assertNotIn("inputs.", block)
            self.assertNotIn("client_payload", block)
            self.assertNotIn("github.event", block)
        self.assertNotIn("secrets.", WORKFLOW)

    def test_every_job_detects_the_call_before_checking_out_this_repository(self) -> None:
        for job in (VERIFY, REPORT):
            steps = job[job.index("\n    steps:") :]
            detect = steps.index("- name: Detect release workflow call")
            checkout = steps.index("- name: Checkout")
            self.assertLess(detect, checkout)
            self.assertLess(detect, steps.index("- name:", steps.index("\n", detect)) + 1)
            self.assertIn("JOB_CONTEXT: ${{ toJSON(job) }}", steps[:checkout])
            self.assertIn("CALLER_WORKFLOW_REF: ${{ github.workflow_ref }}", steps[:checkout])
            self.assertIn('echo "RELEASE_WORKFLOW_CALL=true"', steps[:checkout])
            self.assertIn('echo "COOKBOOK_COMMIT=$JOB_WORKFLOW_SHA"', steps[:checkout])
            self.assertIn("grep -Eqx '[0-9a-f]{40}'", steps[:checkout])
            with_block = steps[checkout : steps.index("\n      - name:", checkout)]
            self.assertIn(
                "repository: ${{ env.RELEASE_WORKFLOW_CALL == 'true' && "
                "'cubrid-lab/cubrid-cookbook-python' || github.repository }}",
                with_block,
            )
            self.assertIn("ref: ${{ env.COOKBOOK_COMMIT }}", with_block)
            self.assertIn("persist-credentials: false", with_block)

    def test_call_runs_full_suite_even_from_a_callers_pull_request(self) -> None:
        self.assertIn(
            "EVENT_NAME: ${{ env.RELEASE_WORKFLOW_CALL == 'true' && 'workflow_call' "
            "|| github.event_name }}",
            VERIFY,
        )
        self.assertNotIn("if: github.event_name != 'pull_request'\n", VERIFY)
        call_guard = (
            "if: github.event_name != 'pull_request' || env.RELEASE_WORKFLOW_CALL == 'true'"
        )
        for step_name in (
            "Install pytest suite dependencies (non-PR runs only)",
            "Run Flask and FastAPI pytest suites (non-PR runs only)",
            "Run async-worker database tasks (non-PR runs only)",
            "Run Django SQLAlchemy bridge (non-PR runs only)",
            "Start isolated dashboard CUBRID (non-PR runs only)",
            "Wait for isolated dashboard CUBRID",
            "Run isolated Streamlit dashboard pytest suite",
        ):
            start = VERIFY.index(f"- name: {step_name}")
            end = VERIFY.find("\n      - name:", start + 1)
            block = VERIFY[start : end if end != -1 else None]
            self.assertIn(call_guard, block, step_name)

    def test_report_job_runs_for_calls(self) -> None:
        self.assertIn("|| inputs.package != '') }}", REPORT[: REPORT.index("\n    steps:")])

    def test_concurrency_never_shares_or_cancels_a_release_group(self) -> None:
        concurrency = " ".join(
            HEADER[HEADER.index("\nconcurrency:") : HEADER.index("\npermissions:")].split()
        )
        release = (
            "(github.event_name == 'repository_dispatch' || "
            "(inputs.package && inputs.package != 'latest'))"
        )
        self.assertIn(
            release + " && format('-run-{0}-{1}', github.run_id, github.run_attempt)",
            concurrency,
        )
        self.assertIn("cancel-in-progress: >- ${{ !" + release + " }}", concurrency)
        self.assertNotIn("github.event.inputs", concurrency)

    def test_minimal_permissions(self) -> None:
        permissions = HEADER[HEADER.index("\npermissions:") : HEADER.index("\nenv:")]
        self.assertEqual(
            [line.strip() for line in permissions.splitlines() if line and line[0] == " "],
            ["contents: read"],
        )
        self.assertNotIn("permissions:", JOBS)


if __name__ == "__main__":
    unittest.main()
