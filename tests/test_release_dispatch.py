"""Exact release dispatch validation without a database, network or real retry delays."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_dispatch", ROOT / "scripts/release_smoke.py")
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class ReleaseDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.event = self.root / "event.json"
        self.state = self.root / "state.json"
        self.constraints = self.root / "constraints.txt"
        self.versions = {
            "pycubrid": "1.7.1",
            "sqlalchemy-cubrid": "1.7.1",
            "cubrid-mcp-server": "0.4.0",
        }
        self.urls = {name: None for name in self.versions}
        distribution = patch.object(smoke.metadata, "distribution", self.distribution)
        distribution.start()
        self.addCleanup(distribution.stop)

    def distribution(self, name: str) -> SimpleNamespace:
        if name not in self.versions:
            raise smoke.metadata.PackageNotFoundError(name)
        return SimpleNamespace(version=self.versions[name], read_text=lambda _: self.urls[name])

    def payload(self, package="pycubrid", ref="v1.7.1") -> None:
        self.event.write_text(json.dumps({"client_payload": {"package": package, "ref": ref}}))

    def manual(self, package="pycubrid", version="1.7.1") -> None:
        self.event.write_text(json.dumps({"inputs": {"package": package, "version": version}}))

    def test_supported_packages_select_exact_version(self) -> None:
        for package, version in self.versions.items():
            with self.subTest(package=package):
                self.payload(package, "v" + version)
                request = smoke.read_request("repository_dispatch", self.event)
                self.assertEqual(
                    request,
                    {
                        "package": package,
                        "ref": "v" + version,
                        "version": version,
                        "request_id": None,
                    },
                )
                with (
                    patch.object(smoke.subprocess, "run") as install,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                ):
                    smoke.select_releases("repository_dispatch", self.event, self.constraints)
                command = install.call_args.args[0]
                self.assertIn(package + "==" + version, command)
                self.assertFalse(any("git+" in argument for argument in command))
                self.assertEqual(install.call_args.kwargs["timeout"], 60)
                self.assertIn("--constraint", bootstrap.call_args.args[0])

    def test_invalid_event_invokes_no_install_or_sleep(self) -> None:
        invalid = [
            ("unknown", "v1.7.1"),
            ("pycubrid --help", "v1.7.1"),
            ("pycubrid", "main"),
            ("pycubrid", "v1.7"),
            ("pycubrid", "v01.7.1"),
            ("pycubrid", "v1.7.1\n"),
            ("pycubrid", "v1.7.1;echo hello"),
            ("pycubrid", "git+https://example.com/main"),
            ("pycubrid", None),
        ]
        for package, ref in invalid:
            with self.subTest(package=package, ref=ref):
                self.payload(package, ref)
                with (
                    patch.object(smoke.subprocess, "run") as install,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                    patch.object(smoke.time, "sleep") as sleep,
                ):
                    with self.assertRaises(ValueError):
                        smoke.select_releases("repository_dispatch", self.event, self.constraints)
                install.assert_not_called()
                bootstrap.assert_not_called()
                sleep.assert_not_called()

    def test_regular_event_keeps_generic_selection(self) -> None:
        with (
            patch.object(smoke.subprocess, "run") as exact,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
        ):
            smoke.select_releases("push", None, self.constraints)
        exact.assert_not_called()
        self.assertNotIn("--constraint", bootstrap.call_args.args[0])

    def test_delayed_publication_retries_then_succeeds(self) -> None:
        self.payload()
        missing = subprocess.CalledProcessError(1, "pip")
        with (
            patch.object(
                smoke.subprocess,
                "run",
                side_effect=[missing, missing, SimpleNamespace(returncode=0)],
            ) as install,
            patch.object(smoke.subprocess, "check_call"),
            patch.object(smoke.time, "sleep") as sleep,
        ):
            smoke.select_releases("repository_dispatch", self.event, self.constraints)
        self.assertEqual(install.call_count, 3)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(10), unittest.mock.call(10)])

    def test_unpublished_release_fails_after_finite_attempts(self) -> None:
        self.payload()
        with (
            patch.object(
                smoke.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")
            ) as install,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            patch.object(smoke.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                smoke.select_releases("repository_dispatch", self.event, self.constraints)
        self.assertEqual(install.call_count, 6)
        self.assertEqual(sleep.call_count, 5)
        bootstrap.assert_not_called()

    def test_installer_timeout_exhausts_budget(self) -> None:
        self.payload()
        with (
            patch.object(
                smoke.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 60)
            ) as install,
            patch.object(smoke.subprocess, "check_call"),
            patch.object(smoke.time, "sleep"),
        ):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                smoke.select_releases("repository_dispatch", self.event, self.constraints)
        self.assertEqual(install.call_count, 6)

    def test_successful_installer_cannot_select_wrong_version(self) -> None:
        self.payload()
        self.versions["pycubrid"] = "1.7.0"
        with (
            patch.object(smoke.subprocess, "run"),
            patch.object(smoke.subprocess, "check_call") as bootstrap,
        ):
            with self.assertRaisesRegex(ValueError, "requested"):
                smoke.select_releases("repository_dispatch", self.event, self.constraints)
        bootstrap.assert_not_called()

    def test_requested_mcp_is_pinned_and_checked_after_all_installs(self) -> None:
        self.payload("cubrid-mcp-server", "v0.4.0")
        request = smoke.read_request("repository_dispatch", self.event)
        smoke.freeze(self.state, self.constraints, request)
        self.assertIn("cubrid-mcp-server==0.4.0", self.constraints.read_text())
        smoke.verify(self.state)
        self.versions["cubrid-mcp-server"] = "0.4.1"
        with self.assertRaisesRegex(ValueError, "requested"):
            smoke.verify(self.state)

    def test_same_version_requested_vcs_origin_fails(self) -> None:
        self.payload("cubrid-mcp-server", "v0.4.0")
        request = smoke.read_request("repository_dispatch", self.event)
        smoke.freeze(self.state, self.constraints, request)
        self.urls["cubrid-mcp-server"] = '{"vcs_info": {"commit_id": "123"}}'
        with self.assertRaisesRegex(ValueError, "not a direct URL"):
            smoke.verify(self.state)

    def test_requested_mcp_never_uses_fallback(self) -> None:
        self.payload("cubrid-mcp-server", "v0.4.0")
        smoke.freeze(
            self.state, self.constraints, smoke.read_request("repository_dispatch", self.event)
        )
        with patch.object(smoke.subprocess, "check_call") as install:
            smoke.install_mcp(self.state)
        install.assert_not_called()

    def test_nonrequested_mcp_preserves_fallback_and_discloses_origin(self) -> None:
        smoke.freeze(self.state, self.constraints)
        with patch.object(
            smoke.subprocess, "check_call", side_effect=[subprocess.CalledProcessError(1, "pip"), 0]
        ) as install:
            smoke.install_mcp(self.state)
        self.assertIn(
            "git+https://github.com/cubrid-lab/cubrid-mcp-server.git@v0.4.0",
            install.call_args.args[0],
        )
        self.urls["cubrid-mcp-server"] = '{"vcs_info": {"commit_id": "123"}}'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            smoke.summary("push", None, self.state, "abc123", "11.2", "success")
        self.assertIn("direct URL / VCS", output.getvalue())

    def test_workflow_final_summary_always_runs_after_tests(self) -> None:
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text()
        report = workflow.index("name: Report release smoke result")
        self.assertGreater(report, workflow.index("name: Run make verify"))
        self.assertIn("if: always()", workflow[report:])
        self.assertIn("SMOKE_RESULT: ${{ job.status }}", workflow[report:])
        self.assertIn("CUBRID_SERVER_VERSION=", workflow)

    def test_inline_workflow_commands_with_colon_are_yaml_quoted(self) -> None:
        # Shell quotes around a label do not quote the surrounding YAML scalar.
        # This narrow guard catches that regression; actual YAML parsing is separate.
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text()
        for line in workflow.splitlines():
            if line.lstrip().startswith("run:"):
                value = line.lstrip()[4:].strip()
                if ": " in value:
                    self.assertTrue(value.startswith(("|", ">", "'", '"')), line)

    def test_summary_exposes_request_actual_origin_commit_server_and_result(self) -> None:
        self.payload()
        smoke.freeze(
            self.state, self.constraints, smoke.read_request("repository_dispatch", self.event)
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            smoke.summary(
                "repository_dispatch", self.event, self.state, "abc123", "11.4.6", "success"
            )
        text = output.getvalue()
        for expected in (
            "v1.7.1",
            "1.7.1",
            "package index",
            "abc123",
            "11.4.6",
            "success",
            "passed",
        ):
            self.assertIn(expected, text)

    def test_failure_summary_discloses_missing_packages(self) -> None:
        self.payload("cubrid-mcp-server", "v0.4.1")
        del self.versions["cubrid-mcp-server"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            smoke.summary(
                "repository_dispatch", self.event, self.state, "abc123", "unavailable", "failure"
            )
        text = output.getvalue()
        self.assertIn("v0.4.1", text)
        self.assertIn("unavailable", text)
        self.assertIn("failure", text)
        self.assertNotIn("| Verification | passed |", text)

    def test_final_summary_cannot_claim_success_after_requested_drift(self) -> None:
        self.payload()
        smoke.freeze(
            self.state, self.constraints, smoke.read_request("repository_dispatch", self.event)
        )
        self.versions["pycubrid"] = "1.7.2"
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            self.assertRaisesRegex(ValueError, "successful smoke"),
        ):
            smoke.summary(
                "repository_dispatch", self.event, self.state, "abc123", "11.4", "success"
            )
        self.assertIn("| Verification | failed |", output.getvalue())
        self.assertIn("| Result | failure |", output.getvalue())

    def test_manual_inputs_select_exact_version_through_dispatch_path(self) -> None:
        for package, version in self.versions.items():
            for spelled in (version, "v" + version):
                with self.subTest(package=package, version=spelled):
                    self.manual(package, spelled)
                    request = smoke.read_request("workflow_dispatch", self.event)
                    self.assertEqual(
                        request,
                        {
                            "package": package,
                            "ref": "v" + version,
                            "version": version,
                            "request_id": None,
                        },
                    )
                    with (
                        patch.object(smoke.subprocess, "run") as install,
                        patch.object(smoke.subprocess, "check_call") as bootstrap,
                    ):
                        smoke.select_releases("workflow_dispatch", self.event, self.constraints)
                    command = install.call_args.args[0]
                    self.assertIn(package + "==" + version, command)
                    self.assertIn("https://pypi.org/simple", command)
                    self.assertIn("--constraint", bootstrap.call_args.args[0])
                    smoke.freeze(self.state, self.constraints, request)
                    self.assertIn(package + "==" + version, self.constraints.read_text())
                    smoke.verify(self.state)

    def test_manual_run_without_release_keeps_latest_selection(self) -> None:
        events = [
            {},
            {"inputs": None},
            {"inputs": {}},
            {"inputs": {"package": "latest", "version": ""}},
            {"inputs": {"package": "", "version": ""}},
        ]
        for event in events:
            with self.subTest(event=event):
                self.event.write_text(json.dumps(event))
                self.assertIsNone(smoke.read_request("workflow_dispatch", self.event))
                with (
                    patch.object(smoke.subprocess, "run") as exact,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                ):
                    smoke.select_releases("workflow_dispatch", self.event, self.constraints)
                exact.assert_not_called()
                self.assertNotIn("--constraint", bootstrap.call_args.args[0])

    def test_invalid_manual_inputs_invoke_no_install_or_sleep(self) -> None:
        invalid = [
            ("unknown", "1.7.1"),
            ("pycubrid --help", "1.7.1"),
            ("latest", "1.7.1"),
            ("", "v1.7.1"),
            (None, "1.7.1"),
            ("pycubrid", ""),
            ("pycubrid", None),
            ("pycubrid", "latest"),
            ("pycubrid", "main"),
            ("pycubrid", "1.7"),
            ("pycubrid", "01.7.1"),
            ("pycubrid", "vv1.7.1"),
            ("pycubrid", "V1.7.1"),
            ("pycubrid", " 1.7.1"),
            ("pycubrid", "1.7.1\n"),
            ("pycubrid", "1.7.1rc1"),
            ("pycubrid", "1.7.1;echo hello"),
            ("pycubrid", "$(echo 1.7.1)"),
        ]
        cases = [{"inputs": {"package": p, "version": v}} for p, v in invalid]
        cases += [{"inputs": ["pycubrid", "1.7.1"]}, {"inputs": "pycubrid==1.7.1"}, []]
        for event in cases:
            with self.subTest(event=event):
                self.event.write_text(json.dumps(event))
                with (
                    patch.object(smoke.subprocess, "run") as install,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                    patch.object(smoke.time, "sleep") as sleep,
                ):
                    with self.assertRaises(ValueError):
                        smoke.select_releases("workflow_dispatch", self.event, self.constraints)
                install.assert_not_called()
                bootstrap.assert_not_called()
                sleep.assert_not_called()

    def test_manual_version_without_package_names_the_problem(self) -> None:
        for package in ("latest", "", None):
            with self.subTest(package=package):
                self.manual(package, "1.8.0")
                with self.assertRaisesRegex(ValueError, "requires a non-latest package"):
                    smoke.read_request("workflow_dispatch", self.event)

    def test_manual_release_retries_delayed_publication_then_fails_bounded(self) -> None:
        self.manual()
        missing = subprocess.CalledProcessError(1, "pip")
        with (
            patch.object(
                smoke.subprocess, "run", side_effect=[missing, SimpleNamespace(returncode=0)]
            ) as install,
            patch.object(smoke.subprocess, "check_call"),
            patch.object(smoke.time, "sleep") as sleep,
        ):
            smoke.select_releases("workflow_dispatch", self.event, self.constraints)
        self.assertEqual(install.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        with (
            patch.object(smoke.subprocess, "run", side_effect=missing) as install,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            patch.object(smoke.time, "sleep"),
        ):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                smoke.select_releases("workflow_dispatch", self.event, self.constraints)
        self.assertEqual(install.call_count, 6)
        bootstrap.assert_not_called()

    def test_manual_release_rejects_wrong_installed_version(self) -> None:
        self.manual("sqlalchemy-cubrid", "1.8.0")
        with (
            patch.object(smoke.subprocess, "run"),
            patch.object(smoke.subprocess, "check_call") as bootstrap,
        ):
            with self.assertRaisesRegex(ValueError, "requested"):
                smoke.select_releases("workflow_dispatch", self.event, self.constraints)
        bootstrap.assert_not_called()

    def test_manual_release_summary_reports_request_installed_and_origin(self) -> None:
        self.manual("pycubrid", "v1.7.1")
        smoke.freeze(
            self.state, self.constraints, smoke.read_request("workflow_dispatch", self.event)
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            smoke.summary("workflow_dispatch", self.event, self.state, "abc123", "11.4", "success")
        text = output.getvalue()
        self.assertIn("| Request | manual release run: pycubrid v1.7.1 |", text)
        self.assertIn("| pycubrid | 1.7.1 | 1.7.1 | package index |", text)
        self.assertIn("| Verification | passed |", text)

    def test_invalid_manual_summary_cannot_claim_success(self) -> None:
        self.manual("pycubrid", "main")
        smoke.freeze(self.state, self.constraints)
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            self.assertRaisesRegex(ValueError, "successful smoke"),
        ):
            smoke.summary("workflow_dispatch", self.event, self.state, "abc123", "11.4", "success")
        self.assertIn("invalid release request", output.getvalue())
        self.assertIn("| Result | failure |", output.getvalue())

    def test_workflow_manual_inputs_are_allowlisted_and_never_interpolated(self) -> None:
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text()
        manual = workflow[workflow.index("  workflow_dispatch:") : workflow.index("concurrency:")]
        for option in (smoke.MANUAL_LATEST, *smoke.PACKAGES):
            self.assertIn(f"          - {option}\n", manual)
        self.assertIn("default: latest", manual)
        self.assertIn("type: choice", manual)
        # Request fields may key the concurrency group, but job steps must read them
        # from GITHUB_EVENT_PATH (via release_smoke.py), never via interpolation.
        jobs = workflow[workflow.index("\njobs:") :]
        self.assertNotIn("inputs.", jobs)
        self.assertNotIn("client_payload", jobs)
        header = workflow[: workflow.index("\njobs:")]
        concurrency = header[header.index("\nconcurrency:") :]
        for key in (
            "github.event_name",
            "github.event.inputs.package || github.event.client_payload.package || 'none'",
            "github.event.inputs.version || github.event.client_payload.ref || 'none'",
            "github.event.inputs.request_id || github.event.client_payload.request_id || 'none'",
            "github.event_name == 'repository_dispatch'",
            "github.event.inputs.package != 'latest'",
        ):
            self.assertIn(key, " ".join(concurrency.split()))
        self.assertNotIn("cancel-in-progress: true", concurrency)


if __name__ == "__main__":
    unittest.main()
