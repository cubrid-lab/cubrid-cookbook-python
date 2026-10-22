"""Make command contracts exercised with temporary, database-free recipes."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def spawn_sleeper_code(pid_file: Path) -> str:
    """Python code that starts a grandchild sleeper and waits until it wrote its pid."""
    grandchild = (
        f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    )
    return (
        "import os, subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "deadline = time.monotonic() + 5\n"
        f"while time.monotonic() < deadline and not (os.path.exists({str(pid_file)!r})"
        f" and os.path.getsize({str(pid_file)!r})):\n"
        "    time.sleep(0.01)\n"
    )


class OrphanChecks(unittest.TestCase):
    def read_pid(self, pid_file: Path) -> int:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            text = pid_file.read_text(encoding="utf-8") if pid_file.exists() else ""
            if text:
                pid = int(text)
                self.addCleanup(self.force_kill, pid)
                return pid
            time.sleep(0.01)
        self.fail(f"no pid written to {pid_file}")

    @staticmethod
    def force_kill(pid: int) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)

    def assert_gone(self, pid: int) -> None:
        # A SIGKILLed orphan is reaped by init asynchronously; allow a moment.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        with self.assertRaises(ProcessLookupError, msg=f"process {pid} outlived the runner"):
            os.kill(pid, 0)


class VerifyCommandTests(OrphanChecks):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in (
            "check_expected_coverage.py",
            "example_requirements.py",
            "normalize_output.sh",
            "run_example.py",
            "verify_goldens.sh",
        ):
            shutil.copyfile(ROOT / "scripts" / name, scripts / name)

    def example(self, directory: str = "recipes", name: str = "ok", code: str = "print('row')"):
        folder = self.root / directory
        expected = folder / "expected"
        expected.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.py").write_text(code + "\n", encoding="utf-8")
        (expected / f"{name}.expected").write_text("row\n", encoding="utf-8")

    def fake_command(self, name: str, body: str) -> dict[str, str]:
        binaries = self.root / "bin"
        binaries.mkdir(exist_ok=True)
        command = binaries / name
        command.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        command.chmod(0o755)
        return {**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"}

    def verify(
        self,
        paths: str | None = None,
        *,
        env=None,
        normalize: str | None = None,
        timeout: int | None = None,
        stdin: str | None = None,
        target: str = "verify-goldens",
        python: str | None = None,
        extra: tuple[str, ...] = (),
    ):
        command = ["make", "--no-print-directory", "-f", str(ROOT / "Makefile"), target]
        command.append(f"PYTHON={python or sys.executable}")
        if paths is not None:
            command.append(f"VERIFY_PATHS={paths}")
        if normalize is not None:
            command.append(f"NORMALIZE={normalize}")
        if timeout is not None:
            command.append(f"VERIFY_TIMEOUT={timeout}")
        command.extend(extra)
        return subprocess.run(
            command,
            cwd=self.root,
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def assert_counts(self, result, **counts: int) -> None:
        defaults = {
            "passed": 0,
            "mismatch": 0,
            "exec-error": 0,
            "timeout": 0,
            "normalize-error": 0,
            "read-error": 0,
        }
        defaults.update({key.replace("_", "-"): value for key, value in counts.items()})
        summary = result.stdout.rsplit("Results: ", 1)[-1]
        for label, value in defaults.items():
            self.assertIn(f"{value} {label}", summary, result.stdout)

    def test_missing_root_fails(self) -> None:
        self.assertNotEqual(self.verify("missing").returncode, 0)

    def test_empty_roots_fail(self) -> None:
        self.example()
        for paths in ("", "   "):
            with self.subTest(paths=paths):
                self.assertNotEqual(self.verify(paths).returncode, 0)

    def test_non_directory_root_fails(self) -> None:
        (self.root / "file.txt").touch()
        self.assertNotEqual(self.verify("file.txt").returncode, 0)

    def test_zero_expected_targets_fail(self) -> None:
        (self.root / "empty").mkdir()
        self.assertNotEqual(self.verify("empty").returncode, 0)

    def test_orphan_expected_fails(self) -> None:
        expected = self.root / "recipes" / "expected"
        expected.mkdir(parents=True)
        (expected / "orphan.expected").write_text("row\n", encoding="utf-8")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_mixed_orphan_and_valid_recipe_fail(self) -> None:
        self.example()
        (self.root / "recipes/expected/orphan.expected").write_text("row\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("1 passed", result.stdout)

    def test_find_error_cannot_be_hidden_by_sort(self) -> None:
        self.example()
        env = self.fake_command("find", "printf '%s\\n' recipes/expected/ok.expected; exit 7")
        self.assertNotEqual(self.verify(env=env).returncode, 0)

    def test_golden_read_error_cannot_report_a_match(self) -> None:
        self.example()
        env = self.fake_command("cat", "printf '%s\\n' row; exit 7")
        self.assertNotEqual(self.verify(env=env).returncode, 0)

    def test_symlinked_golden_is_still_verified(self) -> None:
        self.example()
        expected = self.root / "recipes/expected/ok.expected"
        source = self.root / "row.txt"
        source.write_text("row\n", encoding="utf-8")
        expected.unlink()
        expected.symlink_to(source)
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed, 0 failed, 0 skipped", result.stdout)

    def test_expected_directory_is_not_silently_omitted(self) -> None:
        self.example()
        self.example(name="unreadable")
        expected = self.root / "recipes/expected/unreadable.expected"
        expected.unlink()
        expected.mkdir()
        self.assertNotEqual(self.verify().returncode, 0)

    def test_recipe_failure_is_reported_and_other_recipes_still_run(self) -> None:
        self.example(name="bad", code="raise SystemExit(7)")
        self.example(name="good")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("1 passed, 1 failed", result.stdout)

    def test_normalizer_failure_is_reported(self) -> None:
        self.example()
        self.assertNotEqual(self.verify(normalize="false").returncode, 0)

    def test_mismatched_golden_fails(self) -> None:
        self.example(code="print('different')")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_full_and_scoped_selection(self) -> None:
        self.example("first")
        self.example("second")
        for paths, count in ((None, 2), ("first", 1), ("first second", 2)):
            with self.subTest(paths=paths):
                result = self.verify(paths)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"{count} passed, 0 failed, 0 skipped", result.stdout)

    def recorder(self) -> Path:
        recorder = self.root / "python"
        recorder.write_text('#!/bin/sh\necho "ARGS $* GATE=$CUBRID_LIVE_GATE"\n', encoding="utf-8")
        recorder.chmod(0o755)
        return recorder

    def test_verify_with_paths_on_the_command_line_fails_and_names_verify_goldens(self) -> None:
        # #437: make verify never silently becomes the partial golden-only check.
        self.example("first")
        for paths in ("first", ".", ""):
            with self.subTest(paths=paths):
                result = self.verify(paths, target="verify", python=str(self.recorder()))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                message = [line for line in result.stderr.splitlines() if "ERROR" in line]
                self.assertEqual(len(message), 1, result.stderr)
                self.assertIn("make verify-goldens", message[0])
                self.assertNotIn("ARGS", result.stdout)
                self.assertNotIn("passed", result.stdout)

    def test_verify_without_paths_runs_the_full_live_gate(self) -> None:
        recorder = self.recorder()
        base = {
            k: v for k, v in os.environ.items() if k not in {"VERIFY_PATHS", "CUBRID_LIVE_GATE"}
        }
        # An exported VERIFY_PATHS (CI writes VERIFY_PATHS=. to GITHUB_ENV) and an
        # ambient CUBRID_LIVE_GATE=0 must neither downgrade nor ungate a bare make verify.
        for extra in ({}, {"VERIFY_PATHS": "first"}, {"CUBRID_LIVE_GATE": "0"}):
            with self.subTest(env=extra):
                result = self.verify(env={**base, **extra}, target="verify", python=str(recorder))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("ARGS scripts/live_gate.py --gate all GATE=1", result.stdout)
                self.assertNotIn("Verifying example outputs", result.stdout)

    def test_golden_results_are_recorded_for_the_live_gate(self) -> None:
        self.example("first")
        self.example("second", code="print('different')")
        results = self.root / "results.tsv"
        result = self.verify(env={**os.environ, "VERIFY_RESULTS": str(results)})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            results.read_text(encoding="utf-8").splitlines(),
            ["PASS\t./first/ok.py", "MISMATCH\t./second/ok.py"],
        )

    def test_expected_file_names_with_spaces(self) -> None:
        self.example(name="two words")
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed, 0 failed, 0 skipped", result.stdout)

    def test_sleeping_script_times_out_and_fails(self) -> None:
        # The child also starts a grandchild sleeper that would keep stdout open.
        pid_file = self.root / "grandchild.pid"
        self.example(
            name="slow",
            code=spawn_sleeper_code(pid_file) + "print('started', flush=True)\ntime.sleep(60)",
        )
        self.example(name="good")
        result = self.verify(timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("⏱ TIMEOUT ./recipes/slow.py", result.stdout)
        self.assertIn("      started", result.stdout)
        self.assert_counts(result, passed=1, timeout=1)
        self.assertIn("1 passed, 1 failed, 0 skipped", result.stdout)
        self.assert_gone(self.read_pid(pid_file))

    def test_grandchild_of_a_finished_script_is_reaped(self) -> None:
        pid_file = self.root / "grandchild.pid"
        self.example(code=spawn_sleeper_code(pid_file) + "print('row')")
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed, 0 failed, 0 skipped", result.stdout)
        self.assert_gone(self.read_pid(pid_file))

    def test_script_exiting_124_is_an_exec_error_not_a_timeout(self) -> None:
        self.example(name="exits124", code="print('not a timeout')\nraise SystemExit(124)")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("✗ EXEC-ERROR ./recipes/exits124.py (exit 124)", result.stdout)
        self.assertNotIn("TIMEOUT ./recipes", result.stdout)
        self.assert_counts(result, exec_error=1)

    def test_script_killed_by_sigterm_reports_exit_143(self) -> None:
        self.example(name="killed", code="import os, signal\nos.kill(os.getpid(), signal.SIGTERM)")
        result = self.verify()
        self.assertIn("✗ EXEC-ERROR ./recipes/killed.py (exit 143)", result.stdout)
        self.assert_counts(result, exec_error=1)

    def test_script_stdin_is_dev_null(self) -> None:
        # make's own stdin has data; the script must see an empty /dev/null instead.
        self.example(
            code=(
                "import os, sys\n"
                "same = os.path.samestat(os.fstat(0), os.stat(os.devnull))\n"
                "print('row' if same and sys.stdin.read() == '' else 'stdin leaked')"
            )
        )
        result = self.verify(stdin="leaked input\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 passed, 0 failed, 0 skipped", result.stdout)

    def test_each_failure_class_has_its_own_label_and_count(self) -> None:
        self.example(name="crash", code="print('before crash')\nraise SystemExit(7)")
        self.example(name="wrong", code="print('different')")
        self.example(name="good")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("✗ EXEC-ERROR ./recipes/crash.py (exit 7)", result.stdout)
        self.assertIn("      before crash", result.stdout)
        self.assertIn("✗ MISMATCH ./recipes/wrong.py", result.stdout)
        self.assertIn("✓ PASS ./recipes/good.py", result.stdout)
        self.assert_counts(result, passed=1, mismatch=1, exec_error=1)
        self.assertIn("1 passed, 2 failed, 0 skipped", result.stdout)

    def test_normalizer_and_read_errors_are_classified(self) -> None:
        self.example()
        result = self.verify(normalize="false")
        self.assertIn("✗ NORMALIZE-ERROR ./recipes/ok.py", result.stdout)
        self.assert_counts(result, normalize_error=1)
        env = self.fake_command("cat", "exit 7")
        result = self.verify(env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("✗ READ-ERROR ./recipes/expected/ok.expected", result.stdout)
        self.assert_counts(result, read_error=1)

    def test_failures_are_annotated_under_github_actions(self) -> None:
        self.example(name="crash", code="raise SystemExit(3)")
        self.example(name="good")
        result = self.verify(env={**os.environ, "GITHUB_ACTIONS": "true"})
        self.assertIn("::error file=recipes/crash.py,title=make verify EXEC-ERROR::", result.stdout)
        self.assertNotIn("recipes/good.py,title", result.stdout)
        result = self.verify(env={k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"})
        self.assertNotIn("::error", result.stdout)

    def test_missing_example_dependency_fails_once_before_running(self) -> None:
        self.example(code="raise SystemExit('must not run')")
        (self.root / "recipes/requirements.txt").write_text(
            "# comment\nno-such-cookbook-distribution>=1\n", encoding="utf-8"
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run `make deps`", result.stderr)
        self.assertIn("no-such-cookbook-distribution", result.stderr)
        self.assertNotIn("EXEC-ERROR", result.stdout)


def run_deps(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `make deps` with pip replaced by a recorder that prints its arguments."""
    return subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            str(ROOT / "Makefile"),
            "deps",
            f"PYTHON={sys.executable}",
            f"PIP={sys.executable} -c 'import sys; print(\"PIP-ARGS\", *sys.argv[1:])'",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )


class DepsCommandTests(unittest.TestCase):
    def test_installs_every_example_requirements_in_one_call(self) -> None:
        result = run_deps(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [line for line in result.stdout.splitlines() if line.startswith("PIP-ARGS ")]
        self.assertEqual(len(commands), 1, result.stdout)
        command = commands[0] + " "
        self.assertIn(" sqlalchemy-cubrid[pycubrid] ", command)
        self.assertIn("PIP-ARGS install pytest pytest-asyncio ", command)
        requirements = sorted(
            path.relative_to(ROOT)
            for path in ROOT.glob("**/requirements.txt")
            if not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
        )
        # Golden-backed examples and the live suites that make verify runs.
        for expected in (
            "fundamentals/pycubrid/requirements.txt",
            "quickstart/5min-fastapi/requirements.txt",
            "templates/ai-agent/requirements.txt",
            "templates/dashboard/requirements.txt",
            "templates/django/requirements.txt",
        ):
            self.assertIn(Path(expected), requirements)
        for path in requirements:
            self.assertIn(f" -r {path.as_posix()} ", command)

    def test_requirements_path_with_whitespace_fails_make_deps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copyfile(
                ROOT / "scripts/example_requirements.py", root / "scripts/example_requirements.py"
            )
            for name in ("good", "has space"):
                (root / name / "expected").mkdir(parents=True)
                (root / name / "requirements.txt").write_text("pytest\n", encoding="utf-8")
            result = run_deps(root)
            helper = subprocess.run(
                [sys.executable, "scripts/example_requirements.py"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("contains whitespace: 'has space/requirements.txt'", result.stderr)
        self.assertNotIn("PIP-ARGS", result.stdout)
        # Every path is validated before any is printed: no partial list.
        self.assertNotEqual(helper.returncode, 0)
        self.assertEqual(helper.stdout, "")

    def test_requirement_discovery_skips_hidden_and_non_golden_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, golden in (
                ("golden", True),
                ("nested/golden", True),
                (".venv/golden", True),
                ("plain", False),
            ):
                (root / name).mkdir(parents=True)
                (root / name / "requirements.txt").touch()
                if golden:
                    (root / name / "expected").mkdir()
            result, every = (
                subprocess.run(
                    [sys.executable, str(ROOT / "scripts/example_requirements.py"), *flags],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for flags in ((), ("--all",))
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["golden/requirements.txt", "nested/golden/requirements.txt"],
        )
        # --all (make deps) adds non-golden examples but still skips hidden directories.
        self.assertEqual(every.returncode, 0, every.stderr)
        self.assertEqual(
            every.stdout.splitlines(),
            ["golden/requirements.txt", "nested/golden/requirements.txt", "plain/requirements.txt"],
        )


class RunExampleTests(OrphanChecks):
    def test_sigterm_and_sighup_to_the_runner_kill_the_script_and_grandchild(self) -> None:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum.name), tempfile.TemporaryDirectory() as directory:
                grandchild_file = Path(directory) / "grandchild.pid"
                child_file = Path(directory) / "child.pid"
                code = (
                    spawn_sleeper_code(grandchild_file)
                    + f"open({str(child_file)!r}, 'w').write(str(__import__('os').getpid()))\n"
                    + "time.sleep(60)"
                )
                runner = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts/run_example.py"),
                        "--timeout",
                        "30",
                        "--",
                        sys.executable,
                        "-c",
                        code,
                    ]
                )
                self.addCleanup(self.force_kill, runner.pid)
                child = self.read_pid(child_file)
                grandchild = self.read_pid(grandchild_file)
                runner.send_signal(signum)
                self.assertEqual(runner.wait(timeout=10), 128 + signum)
                self.assert_gone(child)
                self.assert_gone(grandchild)

    def test_non_posix_exits_with_a_clear_message(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_example", ROOT / "scripts/run_example.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stderr = io.StringIO()
        with mock.patch.object(module.os, "name", "nt"), contextlib.redirect_stderr(stderr):
            code = module.main(["--timeout", "1", "--", "true"])
        self.assertNotEqual(code, 0)
        self.assertIn("run_example.py requires POSIX process groups", stderr.getvalue())

    def _load_run_example(self):
        spec = importlib.util.spec_from_file_location(
            "run_example", ROOT / "scripts/run_example.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_non_finite_timeout_is_a_usage_error_before_any_command_runs(self) -> None:
        # #382: NaN and infinity are not a deadline. They must be rejected by the
        # parser, before run() or Popen is reached.
        module = self._load_run_example()
        for value in ("nan", "inf", "1e309", "NaN", "Infinity"):
            with self.subTest(timeout=value):
                stderr = io.StringIO()
                with (
                    mock.patch.object(module, "run") as run,
                    mock.patch.object(module.subprocess, "Popen") as popen,
                    contextlib.redirect_stderr(stderr),
                    self.assertRaises(SystemExit) as raised,
                ):
                    module.main(["--timeout", value, "--", "never-executed"])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("finite positive --timeout", stderr.getvalue())
                run.assert_not_called()
                popen.assert_not_called()

    def test_finite_fractional_timeout_reaches_run(self) -> None:
        module = self._load_run_example()
        with mock.patch.object(module, "run", return_value=0) as run:
            self.assertEqual(module.main(["--timeout", "0.25", "--", "true"]), 0)
        run.assert_called_once_with(["true"], 0.25)


def make_dry_run(target: str, *extra: str, cwd: Path = ROOT) -> list[str]:
    """The recipe lines `make -n` would run for ``target`` (prerequisites included)."""
    result = subprocess.run(
        ["make", "--no-print-directory", "-n", "-f", str(ROOT / "Makefile"), target, *extra],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def make_rule(target: str) -> str:
    """The Makefile rule of ``target``: its header line and recipe lines."""
    lines = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{target}:"))
    end = start + 1
    while end < len(lines) and (lines[end].startswith(("\t", "ifeq", "endif")) or not lines[end]):
        if not lines[end]:
            break
        end += 1
    return "\n".join(lines[start:end])


class MakeTargetSemanticsTests(unittest.TestCase):
    """#437: predictable target names; only docker-clean destroys data."""

    def test_clean_removes_generated_files_but_never_touches_docker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copyfile(ROOT / "scripts/stage_docs.py", root / "scripts/stage_docs.py")
            calls = root / "docker-calls"
            binaries = root / "bin"
            binaries.mkdir()
            for name in ("docker", "docker-compose"):
                fake = binaries / name
                fake.write_text(f'#!/bin/sh\necho "{name} $*" >> {calls}\n', encoding="utf-8")
                fake.chmod(0o755)
            generated = [
                ".live-evidence/all/summary.json",
                ".pytest_cache/v/cache/nodeids",
                ".ruff_cache/CACHEDIR.TAG",
                "site/index.html",
                "recipes/__pycache__/ok.cpython-312.pyc",
                "recipes/.pytest_cache/README.md",
                "docs/catalog.md",
                "docs/support-matrix.md",
            ]
            kept = ["recipes/ok.py", "docs/index.md", "docs/ko/getting-started.md", "README.md"]
            for name in generated + kept:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("x\n", encoding="utf-8")
            result = subprocess.run(
                ["make", "--no-print-directory", "-f", str(ROOT / "Makefile"), "clean"]
                + [f"PYTHON={sys.executable}"],
                cwd=root,
                env={**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in generated:
                self.assertFalse((root / name).exists(), name)
            for name in kept:
                self.assertTrue((root / name).exists(), name)
            self.assertFalse(calls.exists(), "make clean ran docker")
        self.assertNotIn("DOCKER_COMPOSE", make_rule("clean"))
        self.assertFalse(any("docker" in line for line in make_dry_run("clean")))

    def test_docker_clean_is_the_only_destructive_target(self) -> None:
        self.assertEqual(
            make_dry_run("docker-clean", "DOCKER_COMPOSE=docker compose")[0],
            "docker compose down -v",
        )
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertEqual(makefile.count("down -v"), 1)
        self.assertIn("down -v", make_rule("docker-clean"))
        # up and down keep their names and down keeps the data.
        self.assertEqual(make_dry_run("down"), ["docker compose down"])
        self.assertEqual(make_dry_run("up")[0], "docker compose up -d")

    def test_test_recipe_is_one_runner_invocation_that_includes_test_normalize(self) -> None:
        for target in ("test", "test-offline"):
            with self.subTest(target=target):
                self.assertEqual(
                    make_dry_run(target, "PYTHON=python3"),
                    ["python3 scripts/run_offline_tests.py"],
                )
        listed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_offline_tests.py"), "--list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        commands = listed.stdout.splitlines()
        self.assertIn("bash scripts/test_normalize_output.sh", commands)
        self.assertIn(
            f"{sys.executable} -m unittest discover -s tests -p test_make_commands.py -v",
            commands,
        )
        # One process per suite: every listed command names exactly one suite.
        self.assertEqual(len(commands), len(set(commands)))
        self.assertGreaterEqual(len(commands), 25)

    def test_runner_stops_at_the_first_failing_suite(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_offline_tests", ROOT / "scripts/run_offline_tests.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ran: list[list[str]] = []

        def fake_run(command, cwd):  # noqa: ANN001, ANN202
            ran.append(command)
            return subprocess.CompletedProcess(command, 3 if len(ran) == 2 else 0)

        stderr = io.StringIO()
        with (
            mock.patch.object(module.subprocess, "run", fake_run),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(module.main([]), 1)
        self.assertEqual(len(ran), 2)
        self.assertIn("FAILED (exit 3)", stderr.getvalue())

    def test_verify_goldens_recipe_is_one_script_invocation(self) -> None:
        rule = make_rule("verify-goldens")
        recipe = [line for line in rule.splitlines()[1:] if line.strip()]
        self.assertEqual(len(recipe), 1, rule)
        self.assertIn("bash scripts/verify_goldens.sh $(VERIFY_PATHS)", recipe[0])
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for classification in ("MISMATCH", "EXEC-ERROR", "⏱ TIMEOUT", "Results:", "::error"):
            self.assertNotIn(classification, makefile)

    def test_check_runs_no_tests(self) -> None:
        self.assertTrue(
            make_rule("check").startswith("check: lint format-check check-docs check-coverage ##"),
            make_rule("check"),
        )
        lines = make_dry_run("check", "PYTHON=python3")
        joined = "\n".join(lines)
        self.assertNotIn("run_offline_tests.py", joined)
        self.assertNotIn("test_normalize_output.sh", joined)
        self.assertNotIn("-m pytest", joined)

    def test_only_format_rewrites_files(self) -> None:
        self.assertEqual(make_dry_run("lint", "RUFF=ruff"), ["ruff check ."])
        self.assertEqual(make_dry_run("format-check", "RUFF=ruff"), ["ruff format --check ."])
        self.assertEqual(
            make_dry_run("format", "RUFF=ruff"), ["ruff check --fix .", "ruff format ."]
        )
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertEqual(makefile.count("--fix"), 1)
        self.assertEqual(makefile.count("$(RUFF) format .\n"), 1)

    def test_focused_live_lanes_are_unchanged(self) -> None:
        lanes = {
            "verify-quickstart": "quickstart",
            "verify-performance": "performance",
            "verify-web": "web",
            "verify-django-celery": "django-celery",
            "verify-ai-agent": "ai-agent",
            "verify-dashboard": "dashboard",
            "verify-templates": "web django-celery dashboard",
        }
        for target, lane in lanes.items():
            with self.subTest(target=target):
                self.assertEqual(
                    make_dry_run(target, "PYTHON=python3"),
                    [f"CUBRID_LIVE_GATE=1 python3 scripts/live_gate.py {lane}"],
                )

    def test_help_groups_contributor_commands(self) -> None:
        result = subprocess.run(
            ["make", "--no-print-directory", "-f", str(ROOT / "Makefile"), "help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        groups = [
            "Database",
            "Offline tests",
            "Live verification",
            "Quality checks",
            "Documentation",
        ]
        positions = [text.index(group) for group in groups]
        self.assertEqual(positions, sorted(positions))
        for group, target in zip(
            groups, ("docker-clean", "test-offline", "verify-goldens", "format-check", "docs-check")
        ):
            self.assertLess(text.index(group), text.index(target))


class OfflineWorkflowTests(unittest.TestCase):
    def test_python_compatibility_is_a_small_classified_live_matrix(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        compatibility = workflow.split("  python-compatibility:\n", 1)[1].split(
            "  # Recipe 10 has independent pins", 1
        )[0]
        # The Python list (3.11-3.14 on broad events) comes from scripts/ci_scope.py.
        self.assertIn("python: ${{ fromJSON(needs.classify.outputs.python) }}", compatibility)
        self.assertIn("if: needs.classify.outputs.compat == 'true'", compatibility)
        self.assertIn('cubrid-version: "11.4"', compatibility)
        self.assertIn("python-version: ${{ matrix.python }}", compatibility)
        for recipe in (
            "fundamentals/pycubrid/01_connect.py",
            "fundamentals/sqlalchemy/01_connect_and_session.py",
        ):
            self.assertIn(f"python {recipe}", compatibility)
            self.assertIn(
                recipe.removesuffix(".py").rsplit("/", 1)[0] + "/expected/", compatibility
            )
        self.assertIn("set -euo pipefail", compatibility)
        self.assertIn("diff -u", compatibility)
        self.assertNotIn("make verify", compatibility)
        self.assertNotIn("continue-on-error", compatibility)
        gate = workflow.split("  ci-gate:\n", 1)[1]
        self.assertIn("python-compatibility", gate.split("runs-on:", 1)[0])
        self.assertIn("R_PYTHON_COMPATIBILITY: ${{ needs.python-compatibility.result }}", gate)

    def test_python_compatibility_failure_cancellation_or_skip_blocks_the_gate(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        gate = workflow.split("  ci-gate:\n", 1)[1]
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        names = [
            line.strip().split(":", 1)[0]
            for line in gate.splitlines()
            if "R_" in line and ": ${{" in line
        ]
        self.assertIn("R_PYTHON_COMPATIBILITY", names)
        for result in ("success", "failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                env = {**os.environ, **dict.fromkeys(names, "success")}
                env["W_PYTHON_COMPATIBILITY"] = "true"
                env["R_PYTHON_COMPATIBILITY"] = result
                check = subprocess.run(
                    ["bash", "-c", script], env=env, capture_output=True, text=True, timeout=5
                )
                self.assertEqual(check.returncode == 0, result == "success", check.stdout)

    def test_ci_runs_the_quality_gate_and_the_offline_tests(self) -> None:
        # make check runs no tests (#437), so CI names make test as well.
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("run: make check test\n", workflow)

    def test_driver_main_runs_the_partial_golden_check_by_its_own_name(self) -> None:
        workflow = (ROOT / ".github/workflows/driver-main.yml").read_text(encoding="utf-8")
        self.assertIn('make verify-goldens VERIFY_PATHS="$RECIPES"', workflow)
        self.assertNotIn("make verify VERIFY_PATHS", workflow)

    def test_required_smoke_runs_command_guards_before_dependency_selection(self) -> None:
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text(encoding="utf-8")
        release = workflow.index("name: Check release smoke guards (offline)")
        guards = workflow.index("name: Check Make and readiness guards (offline)")
        selection = workflow.index("name: Cache pip downloads")
        self.assertLess(release, guards)
        self.assertLess(guards, selection)
        for name in ("test_make_commands.py", "test_wait_for_cubrid.py"):
            self.assertIn(name, workflow[guards:selection])

    def test_dashboard_has_its_own_required_live_cubrid_job(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        shared = workflow.index("  pytest-suites:")
        dashboard = workflow.index("  dashboard-pytest:")
        gate = workflow.index("  ci-gate:")
        self.assertNotIn("templates/dashboard/tests", workflow[shared:dashboard])
        self.assertIn("templates/dashboard/tests", workflow[dashboard:gate])
        self.assertIn("needs: [", workflow[gate:])
        self.assertIn("dashboard-pytest", workflow[gate:])
        self.assertIn('cubrid-version: "11.4"', workflow[dashboard:gate])

    def test_async_worker_has_its_own_required_live_cubrid_job(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        worker = workflow.index("  async-worker-pytest:")
        gate = workflow.index("  ci-gate:")
        self.assertIn('cubrid-version: "11.4"', workflow[worker:gate])
        self.assertIn("templates/async-worker/requirements.txt", workflow[worker:gate])
        self.assertIn("templates/async-worker/tests", workflow[worker:gate])
        self.assertIn("async-worker-pytest", workflow[gate:])

    def test_django_bridge_has_its_own_required_live_cubrid_job(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        django = workflow.index("  django-bridge-pytest:")
        gate = workflow.index("  ci-gate:")
        self.assertIn('cubrid-version: "11.4"', workflow[django:gate])
        self.assertIn("templates/django/requirements.txt", workflow[django:gate])
        self.assertIn("templates/django/tests", workflow[django:gate])
        self.assertIn("django-bridge-pytest", workflow[gate:])

    def test_broad_smoke_runs_full_verify_on_job_owned_databases(self) -> None:
        # smoke-test.yml runs the full, fail-closed make verify (scripts/live_gate.py
        # all): goldens, quickstart, performance, web, Django/Celery, AI agent and
        # the dashboard, each live suite on its own job-owned CUBRID (#416).
        workflow = (ROOT / ".github/workflows/smoke-test.yml").read_text(encoding="utf-8")
        start = workflow.index("name: Start CUBRID containers")
        deps = workflow.index("name: Install verification dependencies")
        recorded = workflow.index("name: Record tested versions")
        verify = workflow.index("name: Run make verify")
        repeat = workflow.index("name: Repeat the AI agent lane")
        upload = workflow.index("name: Upload live evidence")
        report = workflow.index("name: Report release smoke result")
        self.assertLess(start, deps)
        self.assertLess(deps, recorded)
        self.assertLess(recorded, verify)
        self.assertLess(verify, repeat)
        self.assertLess(repeat, upload)
        self.assertLess(upload, report)
        for spec in ("cubrid:33000", "cubrid-live:33100", "cubrid-dashboard:33200"):
            self.assertIn(spec, workflow[start:deps])
        step = workflow[verify:repeat]
        self.assertIn("\n          make verify || status=$?\n", step)
        self.assertIn("CUBRID_TEST_URL: cubrid+pycubrid://dba@localhost:33100/testdb", step)
        self.assertIn(
            "CUBRID_DASHBOARD_TEST_URL: cubrid+pycubrid://dba@localhost:33200/testdb", step
        )
        # The broad smoke never names VERIFY_PATHS: on the command line make verify
        # refuses it (#437), and the run must cover every golden.
        self.assertNotIn("VERIFY_PATHS=", workflow)
        self.assertNotIn("VERIFY_PATHS:", workflow)
        self.assertNotIn("continue-on-error", workflow[start:upload])
        # Two sequential AI agent runs on the same database, both kept (#426).
        self.assertIn("make verify-ai-agent", workflow[repeat:upload])
        self.assertIn(".live-evidence/ai-agent-run-1", workflow[repeat:upload])
        self.assertIn(".live-evidence/ai-agent-run-2", workflow[repeat:upload])
        # The dashboard gets its own database instead of replacing the examples one.
        self.assertNotIn("docker stop", workflow)
        self.assertNotIn("templates/dashboard/tests", workflow)
        self.assertIn("if: always()", workflow[report:])
        self.assertIn("SMOKE_RESULT: ${{ job.status }}", workflow[report:])

    def test_flask_fixtures_do_not_delete_dashboard_sales(self) -> None:
        for recipe in ("01-basic-crud", "07-vendor-feed"):
            fixture = ROOT / "templates/flask" / recipe / "tests/conftest.py"
            self.assertNotIn("DROP TABLE IF EXISTS cookbook_sales", fixture.read_text())


if __name__ == "__main__":
    unittest.main()
