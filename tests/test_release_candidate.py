"""Candidate artifact mode of the smoke-test.yml workflow call (#240).

A release workflow passes the wheel its own build job uploaded earlier in the
same run, plus the build job's {"<file>": "<sha256>"} output. The cookbook must
verify the exact bytes and metadata before installing anything, keep the
candidate installed through every later install, label the evidence, and fail
closed on any missing, substituted, corrupt or mismatched input. Published mode
(the default) must stay the exact-PyPI behavior, with no fallback either way.
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_candidate", ROOT / "scripts/release_smoke.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
WORKFLOW = (ROOT / ".github/workflows/smoke-test.yml").read_text()
JOBS = WORKFLOW[WORKFLOW.index("\njobs:") :]
VERIFY = JOBS[: JOBS.index("\n  report:")]
REPORT = JOBS[JOBS.index("\n  report:") :]
CELLS = (("11.2", "3.12"), ("11.4", "3.12"), ("11.4", "3.11"))
RUN = {"id": "42", "attempt": "1", "url": "https://example.test/runs/42", "commit": "abc"}
# Stable across run attempts (no run_attempt), as the documented caller shape uses.
REQUEST_ID = "pycubrid-rc-v1.8.0-42"
SOURCE_SHA = "d" * 40
DESIGN = (ROOT / "docs/internal/rc-verification-design.md").read_text()
CONTRIBUTING = (ROOT / "CONTRIBUTING.md").read_text()
WHEEL = "pycubrid-1.8.0-py3-none-any.whl"
SDIST = "pycubrid-1.8.0.tar.gz"


def setUpModule() -> None:
    """Hermetic: a release job's own RELEASE_* environment (the workflow-level
    RELEASE_INPUT_* call inputs, RELEASE_WORKFLOW_CALL) must not leak into these
    tests, which run inside that job as an offline guard."""
    patcher = patch.dict(os.environ)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
    for name in [name for name in os.environ if name.startswith("RELEASE_")]:
        del os.environ[name]


def build_wheel(path: Path, name: str = "pycubrid", version: str = "1.8.0") -> None:
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pycubrid/__init__.py", f'__version__ = "{version}"\n')
        archive.writestr(
            f"{dist_info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        )
        archive.writestr(f"{dist_info}/RECORD", "")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step(job: str, name: str) -> str:
    start = job.index(f"- name: {name}")
    end = job.find("\n      - name:", start + 1)
    return job[start : end if end != -1 else None]


NAME = re.compile(
    r"\$\{\{ inputs\.mode == 'candidate' && format\('(?P<candidate>[^']*)', inputs\.request_id\)"
    r" \|\| '(?P<published>[^']*)' \}\}(?P<middle>[^$]*)\$\{\{ matrix\.cubrid \}\}"
    r"\$\{\{ matrix\.python != '(?P<default>[^']*)' && format\('(?P<py>[^']*)', matrix\.python\)"
    r" \|\| '' \}\}"
)


def render(expression: str, mode: str, request_id: str, cubrid: str, python: str) -> str:
    """Evaluate the part artifact name expression for one cell."""
    match = NAME.fullmatch(expression)
    assert match is not None, expression
    prefix = match["candidate"].format(request_id) if mode == "candidate" else match["published"]
    suffix = match["py"].format(python) if python != match["default"] else ""
    return f"{prefix}{match['middle']}{cubrid}{suffix}"


class CandidateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.candidate = self.root / "candidate"
        self.candidate.mkdir()
        self.event = self.root / "event.json"
        self.event.write_text(json.dumps({"ref": "refs/heads/main"}))
        self.state = self.root / "state.json"
        self.constraints = self.root / "constraints.txt"
        self.parts = self.root / "parts"
        self.output = self.root / "report" / "release-verification.json"
        self.github_output = self.root / "github-output"
        build_wheel(self.candidate / WHEEL)
        (self.candidate / SDIST).write_bytes(b"sdist bytes")
        self.hashes = {name: digest(self.candidate / name) for name in (WHEEL, SDIST)}
        self.environment = [
            SimpleNamespace(metadata={"Name": "SQLAlchemy"}, version="2.0.40"),
            SimpleNamespace(metadata={"Name": "Flask"}, version="3.1.0"),
        ]
        self.versions = {
            "pycubrid": "1.8.0",
            "sqlalchemy-cubrid": "1.8.0",
            "cubrid-mcp-server": "0.4.0",
        }
        # pip's direct_url.json for each package; None = installed from an index.
        self.direct_urls: dict[str, str | None] = {
            "pycubrid": self.direct_url(),
            "sqlalchemy-cubrid": None,
            "cubrid-mcp-server": None,
        }
        for patcher in (
            patch.object(smoke.metadata, "distribution", self.distribution),
            # The full environment listing (pip freeze-like) of each part.
            patch.object(smoke.metadata, "distributions", lambda: self.environment),
            patch.dict(smoke.os.environ, {smoke.CANDIDATE_DIR_ENV: str(self.candidate)}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        wait = patch.object(smoke, "wait_for_pypi")
        self.wait = wait.start()
        self.addCleanup(wait.stop)

    def direct_url(self, wheel: Path | None = None, sha256: str | None = None) -> str:
        wheel = wheel or (self.candidate / WHEEL)
        sha256 = sha256 or digest(self.candidate / WHEEL)
        return json.dumps(
            {
                "archive_info": {"hash": f"sha256={sha256}", "hashes": {"sha256": sha256}},
                "url": wheel.resolve().as_uri(),
            }
        )

    def distribution(self, name: str) -> SimpleNamespace:
        if name not in self.versions:
            raise smoke.metadata.PackageNotFoundError(name)
        direct_url = self.direct_urls[name]
        return SimpleNamespace(
            version=self.versions[name],
            read_text=lambda file: direct_url if file == "direct_url.json" else None,
        )

    def env(self, **overrides: str) -> dict[str, str]:
        values = {
            "RELEASE_INPUT_PACKAGE": "pycubrid",
            "RELEASE_INPUT_VERSION": "1.8.0",
            "RELEASE_INPUT_REQUEST_ID": REQUEST_ID,
            "RELEASE_INPUT_MODE": "candidate",
            "RELEASE_INPUT_CANDIDATE_ARTIFACT": "release-dist",
            "RELEASE_INPUT_CANDIDATE_HASHES": json.dumps(self.hashes),
            "RELEASE_INPUT_CANDIDATE_SOURCE_SHA": SOURCE_SHA,
        }
        values.update(overrides)
        return values

    def request(self, **overrides: str) -> dict:
        return smoke.read_request("workflow_call", self.event, self.env(**overrides))

    def select(self, **overrides: str) -> tuple[object, object]:
        """Run `select` in candidate mode with pip mocked; return (install, bootstrap)."""
        with (
            patch.dict(smoke.os.environ, self.env(**overrides)),
            patch.object(smoke.subprocess, "run") as install,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            patch.object(smoke.time, "sleep"),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            try:
                smoke.select_releases("workflow_call", self.event, self.constraints)
            finally:
                self.install, self.bootstrap = install, bootstrap
        return install, bootstrap

    def assert_select_fails(self, pattern: str, **overrides: str) -> None:
        with self.assertRaisesRegex(ValueError, pattern):
            self.select(**overrides)
        self.install.assert_not_called()
        self.bootstrap.assert_not_called()
        self.wait.assert_not_called()

    def write_parts(self, cells=CELLS, result: str = "success", env: dict | None = None) -> None:
        env = env or self.env()
        with patch.dict(smoke.os.environ, env):
            request = None
            with contextlib.suppress(ValueError):
                request = smoke.read_request("workflow_call", self.event)
            with contextlib.suppress(ValueError):
                smoke.freeze(self.state, self.constraints, request)
            for cubrid, python in cells:
                directory = self.parts / f"part-{cubrid}-{python}-{len(list(self.parts.glob('*')))}"
                directory.mkdir(parents=True, exist_ok=True)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(ValueError):
                    smoke.summary(
                        "workflow_call",
                        self.event,
                        self.state,
                        "c" * 40,
                        "11.4.0.0150",
                        result,
                        directory / smoke.REPORT_PART,
                        cubrid,
                        python,
                    )

    def report(
        self, verify_result: str = "success", download: str = "success", env: dict | None = None
    ) -> tuple[bool, dict, dict]:
        with (
            patch.dict(smoke.os.environ, env or self.env()),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            passed = smoke.report_releases(
                "workflow_call",
                self.event,
                self.parts,
                verify_result,
                download,
                self.output,
                RUN,
                self.github_output,
            )
        lines = self.github_output.read_text().splitlines()
        self.github_output.unlink()
        return (
            passed,
            json.loads(self.output.read_text()),
            dict(line.split("=", 1) for line in lines),
        )


class CandidateInputTests(CandidateTestCase):
    def test_published_mode_is_the_default_and_unchanged(self) -> None:
        expected = {
            "package": "pycubrid",
            "ref": "v1.8.0",
            "version": "1.8.0",
            "request_id": REQUEST_ID,
        }
        for mode in ({}, {"RELEASE_INPUT_MODE": ""}, {"RELEASE_INPUT_MODE": "published"}):
            env = {
                "RELEASE_INPUT_PACKAGE": "pycubrid",
                "RELEASE_INPUT_VERSION": "1.8.0",
                "RELEASE_INPUT_REQUEST_ID": REQUEST_ID,
                **mode,
            }
            with self.subTest(mode=mode):
                self.assertEqual(smoke.read_request("workflow_call", self.event, env), expected)

    def test_candidate_request_names_the_one_wheel_and_its_digest(self) -> None:
        request = self.request()
        self.assertEqual(request["mode"], "candidate")
        self.assertEqual(
            request["candidate"],
            {
                "artifact": "release-dist",
                "files": self.hashes,
                "wheel": WHEEL,
                "sha256": self.hashes[WHEEL],
                "source_sha": SOURCE_SHA,
            },
        )

    def test_only_a_workflow_call_can_select_candidate_mode(self) -> None:
        # Workflow-level env also carries the call inputs; other events ignore them.
        self.event.write_text(json.dumps({"inputs": {"package": "pycubrid", "version": "1.8.0"}}))
        with patch.dict(smoke.os.environ, self.env()):
            request = smoke.read_request("workflow_dispatch", self.event)
        self.assertNotIn("mode", request)
        self.assertNotIn("candidate", request)

    def test_incompatible_mode_inputs_fail_before_any_install(self) -> None:
        cases = {
            "mode candidate": {"RELEASE_INPUT_MODE": "published"},
            "mode must be": {"RELEASE_INPUT_MODE": "Candidate"},
            "mode must be ": {"RELEASE_INPUT_MODE": "both"},
            "requires a request_id": {"RELEASE_INPUT_REQUEST_ID": ""},
            "candidate_artifact matching": {"RELEASE_INPUT_CANDIDATE_ARTIFACT": ""},
            "candidate_artifact matching ": {"RELEASE_INPUT_CANDIDATE_ARTIFACT": "a b"},
            "candidate_artifact matching  ": {"RELEASE_INPUT_CANDIDATE_ARTIFACT": "x" * 101},
            "1-20 file digests": {"RELEASE_INPUT_CANDIDATE_HASHES": ""},
            "must not contain '--'": {"RELEASE_INPUT_REQUEST_ID": "pycubrid--rc-42"},
            "candidate_source_sha: 40": {"RELEASE_INPUT_CANDIDATE_SOURCE_SHA": ""},
            "candidate_source_sha: 40 ": {"RELEASE_INPUT_CANDIDATE_SOURCE_SHA": "D" * 40},
            "candidate_source_sha: 40  ": {"RELEASE_INPUT_CANDIDATE_SOURCE_SHA": "d" * 39},
        }
        for pattern, overrides in cases.items():
            with self.subTest(overrides=overrides):
                self.assert_select_fails(re.escape(pattern.strip()), **overrides)
        # Published mode with any candidate input is rejected too, not silently ignored.
        names = [name for key, name in smoke.MODE_INPUTS.items() if key != "mode"]
        for name in names:
            env = {**self.env(RELEASE_INPUT_MODE="published"), **dict.fromkeys(names, "")}
            env[name] = "x"
            with self.subTest(published_with=name):
                with self.assertRaisesRegex(ValueError, "require mode candidate"):
                    smoke.read_request("workflow_call", self.event, env)

    def test_validate_fails_when_candidate_mode_is_not_a_candidate_call(self) -> None:
        # The call flag is missing (for example a failed call detection): the event
        # is then read as a push, which must not pass as a validated candidate.
        environ = {**self.env(), "GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(self.event)}
        with (
            patch.dict(smoke.os.environ, environ),
            patch.object(smoke.sys, "argv", ["release_smoke.py", "validate"]),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
            self.assertRaises(SystemExit) as exit_,
        ):
            smoke.main()
        self.assertEqual(exit_.exception.code, 1)
        self.assertIn("not a candidate call", stderr.getvalue())

    def test_validate_command_fails_on_incompatible_inputs(self) -> None:
        for overrides, code in (({}, None), ({"RELEASE_INPUT_REQUEST_ID": ""}, 1)):
            with self.subTest(overrides=overrides):
                environ = {**self.env(**overrides), "RELEASE_WORKFLOW_CALL": "true"}
                with (
                    patch.dict(smoke.os.environ, environ),
                    patch.object(smoke.sys, "argv", ["release_smoke.py", "validate"]),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    if code is None:
                        smoke.main()
                    else:
                        with self.assertRaises(SystemExit) as exit_:
                            smoke.main()
                        self.assertEqual(exit_.exception.code, code)

    def test_invalid_digest_maps_fail_before_any_install(self) -> None:
        good = self.hashes[WHEEL]
        cases = {
            "not JSON": "{",
            "JSON object": json.dumps([WHEEL]),
            "JSON object ": json.dumps({}),
            "JSON object  ": json.dumps({f"f{i}.txt": good for i in range(21)}),
            "64 lowercase hex": json.dumps({WHEEL: good.upper()}),
            "64 lowercase hex ": json.dumps({WHEEL: good[:63]}),
            "64 lowercase hex  ": json.dumps({WHEEL: 1}),
            "invalid file name": json.dumps({"../" + WHEEL: good}),
            "invalid file name ": json.dumps({"dist/" + WHEEL: good}),
            "invalid file name  ": json.dumps({"..pycubrid-1.8.0-py3-none-any.whl": good}),
            "exactly one wheel, found 0": json.dumps({SDIST: good}),
            "exactly one wheel, found 2": json.dumps(
                {WHEEL: good, "pycubrid-1.8.0-cp312-cp312-linux_x86_64.whl": good}
            ),
            "not pycubrid 1.8.0": json.dumps({"sqlalchemy_cubrid-1.8.0-py3-none-any.whl": good}),
            "not pycubrid 1.8.0 ": json.dumps({"pycubrid-1.8.1-py3-none-any.whl": good}),
            "not a wheel filename": json.dumps({"pycubrid-1.8.0.whl": good}),
        }
        for pattern, hashes in cases.items():
            with self.subTest(hashes=hashes):
                self.assert_select_fails(
                    re.escape(pattern.strip()), RELEASE_INPUT_CANDIDATE_HASHES=hashes
                )

    def test_wrong_package_or_version_input_fails_against_the_wheel(self) -> None:
        for overrides in (
            {"RELEASE_INPUT_PACKAGE": "sqlalchemy-cubrid"},
            {"RELEASE_INPUT_VERSION": "1.8.1"},
        ):
            with self.subTest(overrides=overrides):
                self.assert_select_fails("is not", **overrides)


class CandidateArtifactTests(CandidateTestCase):
    def test_verified_wheel_is_installed_without_pypi_wait_or_index_copy(self) -> None:
        install, bootstrap = self.select()
        self.wait.assert_not_called()  # Nothing to wait for: the bytes are local.
        command = install.call_args.args[0]
        self.assertEqual(command[-1], str((self.candidate / WHEEL).resolve()))
        self.assertNotIn("pycubrid==1.8.0", command)
        self.assertIn("--no-cache-dir", command)
        self.assertNotIn(str(self.candidate / SDIST), " ".join(command))  # sdist: hash only
        self.assertEqual(self.constraints.read_text(), "pycubrid==1.8.0\n")
        self.assertIn("--constraint", bootstrap.call_args.args[0])

    def test_missing_artifact_fails_closed(self) -> None:
        for path in self.candidate.iterdir():
            path.unlink()
        self.candidate.rmdir()
        self.assert_select_fails("was not downloaded")

    def test_extra_or_missing_files_fail_closed(self) -> None:
        (self.candidate / "evil.pth").write_text("import os\n")
        self.assert_select_fails(r"unexpected \['evil.pth'\]")
        (self.candidate / "evil.pth").unlink()
        (self.candidate / SDIST).unlink()
        self.assert_select_fails(rf"missing \['{re.escape(SDIST)}'\]")

    def test_substituted_wheel_or_sdist_fails_the_digest(self) -> None:
        build_wheel(self.candidate / WHEEL, version="1.8.0")
        with zipfile.ZipFile(self.candidate / WHEEL, "a") as archive:
            archive.writestr("pycubrid/backdoor.py", "")
        self.assert_select_fails(f"SHA-256 of {re.escape(WHEEL)}")
        build_wheel(self.candidate / WHEEL)
        self.hashes[WHEEL] = digest(self.candidate / WHEEL)
        (self.candidate / SDIST).write_bytes(b"other sdist bytes")
        self.assert_select_fails(f"SHA-256 of {re.escape(SDIST)}")

    def test_corrupt_wheel_fails_even_with_a_matching_digest(self) -> None:
        (self.candidate / WHEEL).write_bytes(b"not a zip archive")
        self.hashes[WHEEL] = digest(self.candidate / WHEEL)
        self.assert_select_fails("not a valid wheel")
        # A readable archive whose member bytes no longer match their CRC.
        build_wheel(self.candidate / WHEEL)
        data = (self.candidate / WHEEL).read_bytes()
        broken = data.replace(b'__version__ = "1.8.0"', b'__version__ = "6.6.6"', 1)
        self.assertNotEqual(broken, data)
        (self.candidate / WHEEL).write_bytes(broken)
        self.hashes[WHEEL] = digest(self.candidate / WHEEL)
        self.assert_select_fails("pycubrid/__init__.py is corrupt")

    def test_wheel_metadata_must_match_package_and_version(self) -> None:
        for name, version in (("sqlalchemy-cubrid", "1.8.0"), ("pycubrid", "1.7.1")):
            with self.subTest(name=name, version=version):
                (self.candidate / WHEEL).unlink()
                build_wheel(self.candidate / WHEEL, name=name, version=version)
                self.hashes[WHEEL] = digest(self.candidate / WHEEL)
                self.assert_select_fails("metadata|METADATA")

    def test_non_regular_files_fail_closed(self) -> None:
        (self.candidate / "nested").mkdir()
        self.assert_select_fails("non-regular file: nested")
        (self.candidate / "nested").rmdir()
        (self.candidate / SDIST).unlink()
        (self.candidate / SDIST).symlink_to(self.candidate / WHEEL)
        self.assert_select_fails("non-regular file")


class CandidateProvenanceTests(CandidateTestCase):
    def test_candidate_must_still_be_installed_after_every_install(self) -> None:
        request = self.request()
        smoke.freeze(self.state, self.constraints, request)
        smoke.verify(self.state)  # The verified wheel, installed directly.
        replacements = {
            # A later install replaced it with the PyPI copy of the same version.
            "package index": None,
            # ... with a VCS checkout.
            "not installed from the verified candidate": json.dumps(
                {"url": "https://github.com/cubrid-lab/pycubrid", "vcs_info": {"commit_id": "0"}}
            ),
            # ... with another local wheel, or one with other bytes.
            "not installed from the verified candidate ": self.direct_url(self.root / WHEEL),
            "installed from a wheel with SHA-256": self.direct_url(sha256="0" * 64),
            # ... or the right URL without any recorded digest.
            "installed from a wheel with SHA-256 None": json.dumps(
                {"url": (self.candidate / WHEEL).resolve().as_uri(), "archive_info": {}}
            ),
            "unreadable": "{",
        }
        for pattern, direct_url in replacements.items():
            with self.subTest(pattern=pattern):
                self.direct_urls["pycubrid"] = direct_url
                with self.assertRaisesRegex(ValueError, pattern.strip()):
                    smoke.verify(self.state)
        self.direct_urls["pycubrid"] = self.direct_url()
        self.versions["pycubrid"] = "1.8.1"
        with self.assertRaisesRegex(ValueError, "changed|differs"):
            smoke.verify(self.state)

    def test_legacy_single_hash_form_is_accepted(self) -> None:
        sha256 = digest(self.candidate / WHEEL)
        url = (self.candidate / WHEEL).resolve().as_uri()
        self.direct_urls["pycubrid"] = json.dumps(
            {"url": url, "archive_info": {"hash": f"sha256={sha256}"}}
        )
        smoke.freeze(self.state, self.constraints, self.request())
        smoke.verify(self.state)

    def test_wheel_replaced_on_disk_after_verification_fails(self) -> None:
        request = self.request()
        smoke.freeze(self.state, self.constraints, request)
        (self.candidate / WHEEL).write_bytes(b"swapped")
        with self.assertRaisesRegex(ValueError, "changed after verification"):
            smoke.verify(self.state)

    def test_other_drivers_still_come_from_the_package_index(self) -> None:
        self.direct_urls["sqlalchemy-cubrid"] = json.dumps({"url": "file:///tmp/x.whl"})
        with self.assertRaisesRegex(ValueError, "sqlalchemy-cubrid must be installed from"):
            smoke.freeze(self.state, self.constraints, self.request())

    def test_requested_mcp_candidate_is_never_reinstalled(self) -> None:
        mcp_wheel = "cubrid_mcp_server-0.4.0-py3-none-any.whl"
        (self.candidate / WHEEL).unlink()
        (self.candidate / SDIST).unlink()
        build_wheel(self.candidate / mcp_wheel, name="cubrid-mcp-server", version="0.4.0")
        hashes = json.dumps({mcp_wheel: digest(self.candidate / mcp_wheel)})
        env = self.env(
            RELEASE_INPUT_PACKAGE="cubrid-mcp-server",
            RELEASE_INPUT_VERSION="0.4.0",
            RELEASE_INPUT_CANDIDATE_HASHES=hashes,
        )
        self.direct_urls["pycubrid"] = None
        self.direct_urls["cubrid-mcp-server"] = self.direct_url(
            self.candidate / mcp_wheel, digest(self.candidate / mcp_wheel)
        )
        with patch.dict(smoke.os.environ, env):
            smoke.freeze(self.state, self.constraints, smoke.read_request("workflow_call", None))
        with patch.object(smoke.subprocess, "check_call") as install:
            smoke.install_mcp(self.state)
        install.assert_not_called()
        self.direct_urls["cubrid-mcp-server"] = None  # Replaced by the PyPI copy.
        with self.assertRaisesRegex(ValueError, "package index"):
            smoke.install_mcp(self.state)

    def test_dependency_substitution_marks_the_part_failed(self) -> None:
        with patch.dict(smoke.os.environ, self.env()):
            smoke.freeze(self.state, self.constraints, self.request())
        self.direct_urls["pycubrid"] = None  # Replaced after freeze.
        self.write_parts(cells=[("11.2", "3.12")])
        part = json.loads(next(self.parts.glob(f"**/{smoke.REPORT_PART}")).read_text())
        self.assertEqual(part["origin"], "package index")
        self.assertEqual(part["verification"], "failed")
        self.assertEqual(part["result"], "failure")
        self.assertIsNone(part["candidate_sha256"])
        self.assertEqual(part["evidence"], "candidate artifact")


class CandidateReportTests(CandidateTestCase):
    def test_passing_candidate_report_labels_evidence_and_identity(self) -> None:
        self.write_parts()
        passed, report, outputs = self.report()
        self.assertTrue(passed, report["reasons"])
        self.assertEqual(report["evidence"], "candidate artifact")
        self.assertEqual(
            report["candidate"],
            {
                "artifact": "release-dist",
                "wheel": WHEEL,
                "source_sha": SOURCE_SHA,
                "files": self.hashes,
                "expected_sha256": self.hashes[WHEEL],
                "candidate_sha256": self.hashes[WHEEL],
            },
        )
        self.assertEqual(len(report["matrix"]), 3)
        for part in report["matrix"]:
            self.assertEqual(part["origin"], "candidate artifact")
            self.assertEqual(part["request_id"], REQUEST_ID)
            self.assertEqual(part["candidate_sha256"], self.hashes[WHEEL])
            self.assertEqual(
                part["packages"],
                {
                    "flask": "3.1.0",
                    "sqlalchemy": "2.0.40",
                    "pycubrid": "1.8.0",
                    "sqlalchemy-cubrid": "1.8.0",
                    "cubrid-mcp-server": "0.4.0",
                },
            )
        self.assertEqual(outputs["artifact"], f"release-candidate-verification-{REQUEST_ID}")
        self.assertEqual(outputs["evidence"], "candidate artifact")
        self.assertEqual(outputs["candidate_sha256"], self.hashes[WHEEL])
        self.assertEqual(outputs["installed_version"], "1.8.0")

    def test_failed_report_names_the_claimed_digest_expected_only(self) -> None:
        self.write_parts(cells=CELLS[:2])
        passed, report, outputs = self.report()
        self.assertFalse(passed)
        self.assertEqual(report["candidate"]["expected_sha256"], self.hashes[WHEEL])
        self.assertIsNone(report["candidate"]["candidate_sha256"])
        self.assertEqual(outputs["candidate_sha256"], "")
        markdown = smoke.report_markdown(report)
        self.assertIn(f"| candidate expected_sha256 | {self.hashes[WHEEL]} |", markdown)
        self.assertIn("| candidate candidate_sha256 | none |", markdown)

    def test_parts_of_another_candidate_request_never_count(self) -> None:
        self.write_parts()
        for path in self.parts.glob(f"**/{smoke.REPORT_PART}"):
            part = json.loads(path.read_text())
            part["request_id"] = REQUEST_ID + "-other"
            path.write_text(json.dumps(part))
        passed, report, _ = self.report()
        self.assertFalse(passed)
        self.assertIn(
            f"CUBRID 11.2: request_id {REQUEST_ID}-other is another request", report["reasons"]
        )

    def test_rerun_failed_cell_replaces_its_own_part(self) -> None:
        """gh run rerun --failed keeps request_id, so the re-run cell's part has the
        same artifact name and replaces (overwrite: true) its failed part."""
        self.write_parts(cells=CELLS[:2])
        self.write_parts(cells=CELLS[2:], result="failure")  # Attempt 1 of the 3.11 cell.
        passed, _, _ = self.report(verify_result="failure")
        self.assertFalse(passed)
        failed = [
            path
            for path in self.parts.glob(f"**/{smoke.REPORT_PART}")
            if json.loads(path.read_text())["python"] == "3.11"
        ]
        self.assertEqual(len(failed), 1)
        failed[0].unlink()  # The re-run upload replaces the same-named artifact.
        failed[0].parent.rmdir()
        self.write_parts(cells=CELLS[2:])  # Attempt 2, same request_id.
        passed, report, _ = self.report()
        self.assertTrue(passed, report["reasons"])

    def test_failed_cancelled_or_skipped_cells_fail_the_report(self) -> None:
        self.write_parts()
        for verify_result in ("failure", "cancelled", "skipped", ""):
            with self.subTest(verify_result=verify_result):
                passed, report, outputs = self.report(verify_result=verify_result)
                self.assertFalse(passed)
                self.assertIn(
                    f"smoke jobs finished with {verify_result or 'unknown'}", report["reasons"]
                )
                self.assertEqual(outputs["candidate_sha256"], "")
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(part_result=result):
                for path in self.parts.glob("*"):
                    for file in path.iterdir():
                        file.unlink()
                    path.rmdir()
                self.write_parts(cells=CELLS[:2])
                self.write_parts(cells=CELLS[2:], result=result)
                passed, report, _ = self.report()
                self.assertFalse(passed)
                self.assertTrue(
                    any(f"result {result}" in reason for reason in report["reasons"]),
                    report["reasons"],
                )

    def test_missing_duplicate_or_unreported_cells_fail_the_report(self) -> None:
        passed, report, _ = self.report()  # No part at all: the report is missing.
        self.assertFalse(passed)
        self.assertIn("no smoke job reported a result", report["reasons"])
        self.write_parts(cells=CELLS[:2])
        passed, report, _ = self.report()
        self.assertFalse(passed)
        self.assertIn("CUBRID 11.4, Python 3.11: no result reported", report["reasons"])
        self.write_parts(cells=CELLS[1:])
        passed, report, _ = self.report()
        self.assertFalse(passed)
        self.assertIn("CUBRID 11.4: reported 2 times", report["reasons"])

    def test_failed_part_download_fails_the_report(self) -> None:
        self.write_parts()
        passed, report, _ = self.report(download="failure")
        self.assertFalse(passed)
        self.assertIn("smoke result download did not succeed: failure", report["reasons"])

    def test_parts_of_another_mode_or_digest_never_count(self) -> None:
        published = {
            key: value for key, value in self.env().items() if key not in smoke.MODE_INPUTS.values()
        }
        self.direct_urls["pycubrid"] = None
        self.write_parts(cells=CELLS[:1], env=published)  # A published-package part.
        self.direct_urls["pycubrid"] = self.direct_url()
        self.write_parts(cells=CELLS[1:])
        passed, report, _ = self.report()
        self.assertFalse(passed)
        self.assertIn(
            "CUBRID 11.2: evidence published package, expected candidate artifact",
            report["reasons"],
        )
        # ... and a candidate part never counts for a published report.
        passed, report, _ = self.report(env=published)
        self.assertFalse(passed)
        self.assertTrue(any("expected published package" in r for r in report["reasons"]))
        # A part that tested another wheel (other digest) fails the report.
        for path in self.parts.glob(f"**/{smoke.REPORT_PART}"):
            part = json.loads(path.read_text())
            part.update(evidence="candidate artifact", origin="candidate artifact")
            part["candidate_sha256"] = "f" * 64
            path.write_text(json.dumps(part))
        passed, report, _ = self.report()
        self.assertFalse(passed)
        self.assertTrue(any("is not the verified candidate" in r for r in report["reasons"]))

    def test_invalid_candidate_request_fails_the_report_without_parts(self) -> None:
        passed, report, outputs = self.report(
            env=self.env(RELEASE_INPUT_CANDIDATE_HASHES=json.dumps({SDIST: "0" * 64}))
        )
        self.assertFalse(passed)
        self.assertTrue(report["reasons"][0].startswith("invalid release request"))
        self.assertIsNone(report["evidence"])
        self.assertEqual(outputs["status"], "failure")

    def test_report_command_records_the_callers_source_commit(self) -> None:
        self.write_parts()
        argv = [
            "release_smoke.py",
            "report",
            "--parts",
            str(self.parts),
            "--verify-result",
            "success",
            "--download-result",
            "success",
            "--output",
            str(self.output),
            "--github-output",
            str(self.github_output),
        ]
        environ = {
            **self.env(),
            "RELEASE_WORKFLOW_CALL": "true",
            "GITHUB_REPOSITORY": "cubrid-lab/pycubrid",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_WORKFLOW_REF": "cubrid-lab/pycubrid/.github/workflows/publish-pypi.yml@refs/heads/main",
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
        self.assertEqual(run["caller_repository"], "cubrid-lab/pycubrid")
        self.assertEqual(run["caller_run_sha"], "a" * 40)
        self.assertNotIn("caller_sha", run)
        # The candidate's build source is the input, not the caller run's GITHUB_SHA.
        report = json.loads(self.output.read_text())
        self.assertEqual(report["candidate"]["source_sha"], SOURCE_SHA)
        self.assertTrue(run["caller_workflow_ref"].endswith("publish-pypi.yml@refs/heads/main"))


class EvidenceLabelTests(CandidateTestCase):
    def test_non_release_runs_are_not_labelled_as_release_evidence(self) -> None:
        self.direct_urls["pycubrid"] = None
        smoke.freeze(self.state, self.constraints)
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            smoke.summary("push", self.event, self.state, "c" * 40, "11.4", "success")
        self.assertIn("| Evidence | none (not release evidence) |", text.getvalue())
        self.assertNotIn("published package", text.getvalue())


class CandidateWorkflowTests(unittest.TestCase):
    def test_candidate_inputs_reach_the_script_as_environment_data(self) -> None:
        header = WORKFLOW[: WORKFLOW.index("\njobs:")]
        env = header[header.index("\nenv:") :]
        for name, variable in smoke.MODE_INPUTS.items():
            self.assertIn(f"  {variable}: ${{{{ inputs.{name} }}}}\n", env)
        self.assertNotIn("inputs.candidate_hashes", JOBS)

    def test_outputs_label_the_evidence_and_the_verified_digest(self) -> None:
        call = WORKFLOW[WORKFLOW.index("\n  workflow_call:") : WORKFLOW.index("\nconcurrency:")]
        outputs = REPORT[REPORT.index("\n    outputs:") : REPORT.index("\n    steps:")]
        for name in ("evidence", "candidate_sha256"):
            self.assertIn(f"value: ${{{{ jobs.report.outputs.{name} }}}}", call)
            self.assertIn(f"{name}: ${{{{ steps.report.outputs.{name} }}}}", outputs)

    def test_artifact_is_downloaded_by_name_from_this_run_before_selection(self) -> None:
        download = step(VERIFY, "Download candidate artifact")
        self.assertIn("if: inputs.mode == 'candidate' && inputs.candidate_artifact != ''", download)
        self.assertIn(
            "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
            download,
        )
        self.assertIn("name: ${{ inputs.candidate_artifact }}", download)
        self.assertIn("path: ${{ runner.temp }}/candidate", download)
        # No other run, repository, token or ID: only the same run's artifact.
        for forbidden in ("run-id", "repository:", "github-token", "artifact-ids", "continue-on"):
            self.assertNotIn(forbidden, download)
        self.assertLess(
            VERIFY.index("- name: Download candidate artifact"),
            VERIFY.index("- name: Select released drivers"),
        )

    def test_request_is_validated_before_the_download(self) -> None:
        validate = step(VERIFY, "Validate candidate request")
        self.assertIn("if: inputs.mode == 'candidate'\n", validate)
        self.assertIn("run: python scripts/release_smoke.py validate", validate)
        self.assertLess(
            VERIFY.index("- name: Validate candidate request"),
            VERIFY.index("- name: Download candidate artifact"),
        )

    def test_candidate_runs_never_save_the_pip_cache(self) -> None:
        saving = step(VERIFY, "Cache pip downloads")
        self.assertIn("if: inputs.mode != 'candidate'", saving)
        restore = step(VERIFY, "Restore pip downloads (candidate mode, never saved)")
        self.assertIn("if: inputs.mode == 'candidate'", restore)
        self.assertIn("uses: actions/cache/restore@", restore)
        self.assertEqual(VERIFY.count("uses: actions/cache@"), 1)

    def test_part_names_keep_published_names_and_never_collide(self) -> None:
        upload = step(VERIFY, "Upload release verification result")
        expression = re.search(r"\n          name: (.*)", upload).group(1)
        published = [render(expression, "published", "", *cell) for cell in CELLS]
        self.assertEqual(
            published,
            [
                "release-verification-part-cubrid-11.2",
                "release-verification-part-cubrid-11.4",
                "release-verification-part-cubrid-11.4-py3.11",
            ],
        )
        candidate = [render(expression, "candidate", REQUEST_ID, *cell) for cell in CELLS]
        download = step(REPORT, "Download smoke job results")
        self.assertIn(
            "pattern: ${{ inputs.mode == 'candidate' && "
            "format('release-candidate-part-{0}--*', inputs.request_id) || "
            "'release-verification-part-*' }}",
            download,
        )
        self.assertEqual(candidate[0], f"release-candidate-part-{REQUEST_ID}--cubrid-11.2")
        pattern = f"release-candidate-part-{REQUEST_ID}--*"
        for name in candidate:
            self.assertFalse(fnmatch.fnmatch(name, "release-verification-part-*"), name)
            self.assertTrue(fnmatch.fnmatch(name, pattern))
        for name in published:
            self.assertFalse(fnmatch.fnmatch(name, pattern))
        # One request_id that is a prefix of another never matches its parts.
        longer = [render(expression, "candidate", REQUEST_ID + "-2", *cell) for cell in CELLS]
        for name in longer:
            self.assertFalse(fnmatch.fnmatch(name, pattern), name)
        # A re-run cell (same request_id) uploads the same name and replaces its part.
        self.assertIn("overwrite: true", upload)

    def test_documented_caller_shapes_keep_request_id_stable(self) -> None:
        """A run_attempt in a candidate request_id breaks gh run rerun --failed."""
        section = DESIGN[DESIGN.index("### 13.5") :]
        shape = section[
            section.index("```yaml") : section.index("```", section.index("```yaml") + 3)
        ]
        self.assertIn("mode: candidate", shape)
        self.assertIn(
            "request_id: pycubrid-rc-v${{ needs.detect.outputs.version }}-${{ github.run_id }}",
            shape,
        )
        self.assertIn("candidate_source_sha: ${{ needs.detect.outputs.sha }}", shape)
        self.assertNotIn("run_attempt", shape)
        for document in (DESIGN[DESIGN.index("## 13.") :], CONTRIBUTING):
            self.assertIn("run_attempt", document)  # The rule is stated...
            self.assertNotIn("request_id: ${{ github.run_attempt", document)

    def test_no_new_trigger_schedule_or_permission(self) -> None:
        triggers = WORKFLOW[WORKFLOW.index("\non:") : WORKFLOW.index("\nconcurrency:")]
        self.assertEqual(triggers.count("cron:"), 1)
        self.assertNotIn("pull_request", triggers.split("workflow_call:")[0].split("\n  push:")[0])
        self.assertNotIn("id-token", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotIn(
            "write", WORKFLOW[WORKFLOW.index("\npermissions:") : WORKFLOW.index("\nenv:")]
        )


if __name__ == "__main__":
    unittest.main()
