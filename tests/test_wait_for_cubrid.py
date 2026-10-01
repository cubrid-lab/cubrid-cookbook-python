"""Readiness command tests use an owned fake Compose process, never Docker."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
WAIT_TIMEOUT = 1.5
PROBE_TIMEOUT = 0.5
PROCESS_MARGIN = 3


class ReadinessCommandTests(unittest.TestCase):
    def test_version_selection_uses_existing_bounded_non_destructive_flow(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("image: cubrid/cubrid:${CUBRID_VERSION:-11.2}", compose)
        support = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
        instructions = support.split("## How to Test Against a Specific Version", 1)[1]
        self.assertIn("make down", instructions)
        self.assertIn("CUBRID_VERSION=11.4 make up", instructions)
        self.assertNotIn("sleep 60", instructions)
        self.assertNotIn("docker compose down -v", instructions)
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("CUBRID_VERSION=11.4 make up", contributing)
        self.assertIn("UP_TIMEOUT", contributing)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        down = makefile.split("\ndown:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("$(DOCKER_COMPOSE) down", down)
        self.assertNotIn("-v", down)
        self.assertNotIn("--volumes", down)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.compose = self.root / "compose.py"
        self.log = self.root / "commands.log"

    def fake_compose(self, mode: str) -> str:
        if self.log.exists():
            self.log.unlink()
        self.compose.write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            f"log = Path({str(self.log)!r})\n"
            "previous = log.read_text() if log.exists() else ''\n"
            "args = sys.argv[1:]\n"
            "with log.open('a') as output: output.write(' '.join(args) + '\\n')\n"
            f"mode = {mode!r}\n"
            "if args[0] == 'exec':\n"
            "    if mode == 'success' or (mode == 'transient' and 'exec' in previous):\n"
            "        raise SystemExit(0)\n"
            "    if mode == 'hang': time.sleep(10)\n"
            "    print('fake database unavailable', file=sys.stderr)\n"
            "    raise SystemExit(7)\n"
            "if mode == 'diagnostics-hang': time.sleep(10)\n"
            "print('fake diagnostics: ' + args[0])\n"
            "if mode == 'diagnostics-fail': raise SystemExit(7)\n",
            encoding="utf-8",
        )
        return shlex.join([sys.executable, str(self.compose)])

    def wait(self, mode: str, *, timeout: str = str(WAIT_TIMEOUT)):
        command = [
            sys.executable,
            str(ROOT / "scripts/wait_for_cubrid.py"),
            "--compose",
            self.fake_compose(mode),
            "--timeout",
            timeout,
            "--probe-timeout",
            str(PROBE_TIMEOUT),
            "--interval",
            "0.01",
        ]
        started = time.monotonic()
        outer_timeout = WAIT_TIMEOUT + 2 * PROBE_TIMEOUT + PROCESS_MARGIN
        result = subprocess.run(command, capture_output=True, text=True, timeout=outer_timeout)
        self.assertLess(time.monotonic() - started, outer_timeout)
        return result

    def test_immediate_success(self) -> None:
        result = self.wait("success")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("logs", self.log.read_text())

    def test_transient_failure_then_success(self) -> None:
        result = self.wait("transient")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.log.read_text().count("exec"), 2)

    def test_failure_shows_bounded_diagnostics_without_cleanup(self) -> None:
        result = self.wait("fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fake database unavailable", result.stdout + result.stderr)
        log = self.log.read_text()
        self.assertIn("ps", log)
        self.assertIn("logs --tail 50 cubrid", log)
        self.assertNotIn("down", log)

    def test_hanging_probe_is_bounded(self) -> None:
        result = self.wait("hang")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stdout + result.stderr)

    def test_failing_or_hanging_diagnostics_cannot_report_success(self) -> None:
        for mode in ("diagnostics-fail", "diagnostics-hang"):
            with self.subTest(mode=mode):
                result = self.wait(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ps", self.log.read_text())
                self.assertIn("logs --tail 50 cubrid", self.log.read_text())
                if mode == "diagnostics-hang":
                    self.assertIn("diagnostics failed", result.stderr)
                else:
                    self.assertIn("exit 7", result.stderr)

    def test_invalid_budget_does_not_run_compose(self) -> None:
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                result = self.wait("success", timeout=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.log.exists())

    def test_make_up_uses_the_bounded_helper(self) -> None:
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-f",
                str(ROOT / "Makefile"),
                "up",
                f"DOCKER_COMPOSE={self.fake_compose('fail')}",
                f"PYTHON={sys.executable}",
                f"UP_TIMEOUT={WAIT_TIMEOUT}",
                f"UP_PROBE_TIMEOUT={PROBE_TIMEOUT}",
                "UP_INTERVAL=0.01",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=WAIT_TIMEOUT + 2 * PROBE_TIMEOUT + PROCESS_MARGIN,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CUBRID readiness failed", result.stdout + result.stderr)
        self.assertIn("fake database unavailable", result.stdout + result.stderr)
        self.assertIn("Compose ps", result.stderr)
        self.assertNotIn("down", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
