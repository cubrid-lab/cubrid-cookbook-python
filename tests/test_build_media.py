"""Exercise media staging with fake converters, without recordings or a database."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    "demo-agent-state.gif",
    "agent-state.mp4",
    "mcp-toolchain.mp4",
    "dashboard-terminal.mp4",
    "raw/dashboard.webm",
    "raw/fastapi.webm",
)
OUTPUTS = {
    "demo-dashboard.gif",
    "demo-fastapi.gif",
    "dashboard.mp4",
    "agent-state.mp4",
    "mcp-toolchain.mp4",
    "demo-agent-state.gif",
    "demo-agent-state.png",
    "demo-fastapi.png",
    "demo-dashboard.png",
}


class BuildMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="media build ")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.artifacts = self.root / ".demo-artifacts"
        for name in INPUTS:
            path = self.artifacts / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"recording: " + name.encode())
        self.out = self.artifacts / "out"
        self.out.mkdir()
        for name in OUTPUTS | {"old-only.txt"}:
            (self.out / name).write_bytes(b"previous: " + name.encode())
        self.previous = self.snapshot(self.out)
        self.inputs = {name: (self.artifacts / name).read_bytes() for name in INPUTS}
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        self.fake(
            "ffmpeg",
            """
            import os, signal, sys
            from pathlib import Path
            log = Path('.demo-artifacts/conversions')
            number = int(log.read_text()) + 1 if log.exists() else 1
            log.write_text(str(number))
            output = Path(sys.argv[-1])
            output.write_bytes(b'converted: ' + output.name.encode())
            if str(number) == os.environ.get('EMPTY_AT'):
                output.write_bytes(b'')
            if str(number) == os.environ.get('FAIL_AT'):
                sys.exit(9)
            if str(number) == os.environ.get('SIGNAL_AT'):
                os.kill(os.getppid(), signal.SIGTERM)
            """,
        )

    def fake(self, name: str, code: str) -> None:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(code), encoding="utf-8")
        path.chmod(0o755)

    @staticmethod
    def snapshot(folder: Path) -> dict[str, bytes]:
        return {
            str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()
        }

    def build(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "demos/build_media.sh")],
            cwd=self.root,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_clean(self) -> None:
        self.assertEqual(list(self.artifacts.glob(".build-media.*")), [])
        self.assertEqual(
            {name: (self.artifacts / name).read_bytes() for name in INPUTS}, self.inputs
        )

    def assert_preserved(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(self.out), self.previous)
        self.assert_clean()

    def test_failed_first_conversion_preserves_previous_set(self) -> None:
        self.assert_preserved(self.build(FAIL_AT="1"))

    def test_failed_later_conversion_preserves_previous_set(self) -> None:
        self.assert_preserved(self.build(FAIL_AT="7"))

    def test_empty_conversion_preserves_previous_set(self) -> None:
        self.assert_preserved(self.build(EMPTY_AT="8"))

    def test_failed_copy_preserves_previous_set(self) -> None:
        self.fake("cp", "import sys; sys.exit(9)\n")
        self.assert_preserved(self.build())

    def test_interruption_preserves_previous_set(self) -> None:
        result = self.build(SIGNAL_AT="4")
        self.assert_preserved(result)
        self.assertEqual(result.returncode, 143)

    def test_missing_input_preserves_previous_set(self) -> None:
        (self.artifacts / INPUTS[-1]).unlink()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing recording:", result.stderr)
        self.assertEqual(self.snapshot(self.out), self.previous)
        self.assertFalse((self.artifacts / "conversions").exists())
        self.assertEqual(list(self.artifacts.glob(".build-media.*")), [])

    def assert_published(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(set(self.snapshot(self.out)), OUTPUTS)
        for name in OUTPUTS:
            expected = (
                self.inputs[name]
                if name == "demo-agent-state.gif"
                else b"converted: " + name.encode()
            )
            self.assertEqual((self.out / name).read_bytes(), expected)
        self.assert_clean()

    def test_success_replaces_entire_previous_set(self) -> None:
        self.assert_published(self.build())

    def test_success_without_previous_set(self) -> None:
        shutil.rmtree(self.out)
        self.assert_published(self.build())

    def test_failed_first_build_leaves_no_output(self) -> None:
        shutil.rmtree(self.out)
        result = self.build(FAIL_AT="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())
        self.assert_clean()

    def fake_publish(self, *, interrupt: bool = False, fail_restore: bool = False) -> None:
        # Use the real rename for backups/restores; fail only the publication boundary.
        move = shutil.which("mv")
        self.assertIsNotNone(move)
        self.fake(
            "mv",
            f"""
            import os, signal, subprocess, sys
            from pathlib import Path
            source, destination = map(Path, sys.argv[-2:])
            if source.name == 'out' and source.parent.name.startswith('.build-media.'):
                sys.exit(9)
            if {fail_restore!r} and source.name == 'previous':
                sys.exit(10)
            code = subprocess.call([{move!r}, *sys.argv[1:]])
            if {interrupt!r} and destination.name == 'previous' and code == 0:
                os.kill(os.getppid(), signal.SIGTERM)
            sys.exit(code)
            """,
        )

    def test_publication_failure_restores_previous_set(self) -> None:
        self.fake_publish()
        self.assert_preserved(self.build())

    def test_interruption_after_backup_restores_previous_set(self) -> None:
        self.fake_publish(interrupt=True)
        result = self.build()
        self.assert_preserved(result)
        self.assertEqual(result.returncode, 143)

    def test_failed_restore_retains_backup_for_recovery(self) -> None:
        self.fake_publish(fail_restore=True)
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        workspaces = list(self.artifacts.glob(".build-media.*"))
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(self.snapshot(workspaces[0] / "previous"), self.previous)
        self.assertIn(str(workspaces[0].relative_to(self.root)), result.stderr)

    def interrupt_publication(self) -> subprocess.CompletedProcess[str]:
        move = shutil.which("mv")
        self.assertIsNotNone(move)
        self.fake(
            "mv",
            f"""
            import os, signal, subprocess, sys
            from pathlib import Path
            source, destination = map(Path, sys.argv[-2:])
            code = subprocess.call([{move!r}, *sys.argv[1:]])
            if source.name == 'out' and source.parent.name.startswith('.build-media.'):
                os.kill(os.getppid(), signal.SIGTERM)
            sys.exit(code)
            """,
        )
        return self.build()

    def test_interruption_after_publication_restores_previous_set(self) -> None:
        result = self.interrupt_publication()
        self.assert_preserved(result)
        self.assertEqual(result.returncode, 143)

    def test_interruption_after_first_publication_leaves_no_output(self) -> None:
        shutil.rmtree(self.out)
        result = self.interrupt_publication()
        self.assertEqual(result.returncode, 143)
        self.assertFalse(self.out.exists())
        self.assert_clean()

    def test_output_symlink_is_rejected_without_touching_target(self) -> None:
        target = self.artifacts / "unrelated"
        self.out.rename(target)
        self.out.symlink_to(target, target_is_directory=True)
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.out.is_symlink())
        self.assertEqual(self.snapshot(target), self.previous)
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
