"""Offline tests for scripts/report_results.py, unittest_junit.py and the runner (#461)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import report_results  # noqa: E402


def load_runner():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location(
        "run_offline_tests", ROOT / "scripts/run_offline_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def junit(cases: str) -> str:
    return f'<testsuites><testsuite name="x">{cases}</testsuite></testsuites>'


class ParseJunitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def parse(self, xml: str) -> dict[str, int] | None:
        path = self.dir / "j.xml"
        path.write_text(xml, encoding="utf-8")
        return report_results.parse_junit(path)

    def test_counts_every_outcome_once(self) -> None:
        counts = self.parse(
            junit(
                '<testcase classname="a" name="ok"/>'
                '<testcase classname="a" name="bad"><failure/></testcase>'
                '<testcase classname="a" name="err"><error/></testcase>'
                '<testcase classname="a" name="skip"><skipped/></testcase>'
                '<testcase classname="a" name="xf"><skipped type="pytest.xfail"/></testcase>'
            )
        )
        self.assertEqual(
            counts,
            {
                "selected": 5,
                "passed": 1,
                "failed": 1,
                "errors": 1,
                "skipped": 1,
                "xfailed": 1,
                "xpassed": 0,
            },
        )

    def test_failed_test_with_erroring_teardown_counts_once_as_error(self) -> None:
        counts = self.parse(
            junit(
                '<testcase classname="a" name="t"><failure/></testcase>'
                '<testcase classname="a" name="t"><error/></testcase>'
            )
        )
        self.assertEqual((counts["selected"], counts["failed"], counts["errors"]), (1, 0, 1))
        self.assertEqual(sum(counts[k] for k in report_results.COUNTS[1:]), counts["selected"])

    def test_missing_and_malformed_files_are_none(self) -> None:
        self.assertIsNone(report_results.parse_junit(self.dir / "absent.xml"))
        self.assertIsNone(self.parse("<testsuite"))


class DecideAndSummaryTests(unittest.TestCase):
    def counts(self, **kw: int) -> dict[str, int]:
        base = dict.fromkeys(report_results.COUNTS, 0)
        base.update(kw)
        base["selected"] = sum(v for k, v in base.items() if k != "selected")
        return base

    def test_decide(self) -> None:
        d = report_results.decide
        self.assertEqual(d(self.counts(passed=2), 0), "PASS")
        self.assertEqual(d(self.counts(passed=2), 1), "FAIL")
        self.assertEqual(d(self.counts(passed=2, failed=1), 0), "FAIL")
        self.assertEqual(d(self.counts(skipped=2), 0), "INCOMPLETE")
        self.assertEqual(d(self.counts(), 0), "INCOMPLETE")
        self.assertEqual(d(None, 0), "INCOMPLETE")
        self.assertEqual(d(None, 2), "FAIL")

    def entry(self, status: str, **kw: int) -> dict:
        return {"name": status, "status": status, "counts": self.counts(**kw)}

    def test_totals_status_and_console_line_agree_with_summary(self) -> None:
        passing = self.entry("PASS", passed=3)
        summary = report_results.build_summary("test", [passing, self.entry("PASS", passed=2)])
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["counts"]["passed"], 5)
        self.assertEqual(summary["schema_version"], report_results.SCHEMA_VERSION)
        self.assertEqual(summary["coverage"], {"measured": False})
        line = report_results.console_line(summary)
        self.assertIn("test: PASS", line)
        self.assertIn("selected=5 passed=5 failed=0", line)
        self.assertIn("coverage=not-measured", line)

        failing = report_results.build_summary("test", [passing, self.entry("FAIL", failed=1)])
        self.assertEqual(failing["status"], "FAIL")
        self.assertIn("suites_not_passing=1", report_results.console_line(failing))
        self.assertIn("failed=1", report_results.console_line(failing))

    def test_not_run_or_incomplete_suites_are_never_pass(self) -> None:
        passing = self.entry("PASS", passed=1)
        self.assertEqual(
            report_results.build_summary("t", [passing], ["x"])["status"], "INCOMPLETE"
        )
        self.assertEqual(
            report_results.build_summary("t", [self.entry("INCOMPLETE", skipped=1)])["status"],
            "INCOMPLETE",
        )
        self.assertEqual(report_results.build_summary("t", [])["status"], "INCOMPLETE")


class ResetResultsDirTests(unittest.TestCase):
    def test_refuses_dangerous_paths(self) -> None:
        for bad in ("", ".", "..", "/", str(ROOT), str(ROOT.parent), str(Path.home())):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                report_results.reset_results_dir(Path(bad), ROOT)

    def test_empties_a_directory_and_recreates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test-results" / "test"
            target.mkdir(parents=True)
            (target / "stale.xml").write_text("old")
            report_results.reset_results_dir(target, ROOT)
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])


class UnittestJunitTests(unittest.TestCase):
    def run_runner(self, source: str) -> tuple[int, dict[str, int] | None]:
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_sample.py").write_text(textwrap.dedent(source), encoding="utf-8")
            out = Path(tmp) / "out" / "j.xml"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/unittest_junit.py"),
                    str(out),
                    "discover",
                    "-s",
                    str(tests),
                    "-p",
                    "test_sample.py",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tmp,
            )
            return proc.returncode, report_results.parse_junit(out)

    def test_pass_fail_error_skip_are_counted(self) -> None:
        code, counts = self.run_runner(
            """
            import unittest
            class T(unittest.TestCase):
                def test_ok(self): pass
                def test_bad(self): self.fail("x")
                def test_err(self): raise RuntimeError("y")
                @unittest.skip("s")
                def test_skip(self): pass
                @unittest.expectedFailure
                def test_xf(self): self.fail("expected")
                def test_sub(self):
                    with self.subTest(i=1):
                        self.fail("sub")
            """
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            counts,
            {
                "selected": 6,
                "passed": 1,
                "failed": 2,
                "errors": 1,
                "skipped": 1,
                "xfailed": 1,
                "xpassed": 0,
            },
        )

    def test_all_passing_exits_zero(self) -> None:
        code, counts = self.run_runner(
            """
            import unittest
            class T(unittest.TestCase):
                def test_ok(self): pass
            """
        )
        self.assertEqual((code, counts["passed"], counts["selected"]), (0, 1, 1))


class RunnerAggregationTests(unittest.TestCase):
    """run_offline_tests.main with a faked subprocess: aggregation, status, exit code."""

    def run_main(self, fail_at: int | None) -> tuple[int, dict, str]:
        runner = load_runner()
        calls: list[list[str]] = []

        def fake_run(command, cwd):  # noqa: ANN001, ANN202
            calls.append(command)
            code = 3 if len(calls) == fail_at else 0
            for arg in command:
                path = arg.removeprefix("--junitxml=")
                if path.endswith(".xml"):
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    bad = '<failure message="m"/>' if code else ""
                    Path(path).write_text(
                        junit(
                            f'<testcase classname="c" name="t">{bad}</testcase>'
                            '<testcase classname="c" name="u"/>'
                        ),
                        encoding="utf-8",
                    )
            return subprocess.CompletedProcess(command, code)

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "test-results" / "test"
            with (
                mock.patch.object(runner.subprocess, "run", fake_run),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code = runner.main(["--results-dir", str(results)])
            summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
            files = sorted(p.name for p in (results / "junit").iterdir())
        self.assertEqual(
            len(files), len(summary["suites"]) - sum(s["junit"] is None for s in summary["suites"])
        )
        return code, summary, out.getvalue()

    def test_all_suites_pass(self) -> None:
        code, summary, out = self.run_main(None)
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["not_run"], [])
        self.assertEqual(len(summary["suites"]), len(load_runner().SUITES))
        self.assertEqual(
            summary["counts"]["passed"], sum(s["counts"]["passed"] for s in summary["suites"])
        )
        self.assertEqual(
            out.splitlines()[-1].split(" -> ")[0], report_results.console_line(summary)
        )

    def test_failing_suite_is_fail_exit_one_and_stops_the_run(self) -> None:
        code, summary, out = self.run_main(2)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual([s["status"] for s in summary["suites"]], ["PASS", "FAIL"])
        self.assertEqual(len(summary["not_run"]), len(load_runner().SUITES) - 2)
        self.assertIn("test: FAIL", out.splitlines()[-1])
        self.assertIn(f"not_run={len(summary['not_run'])}", out.splitlines()[-1])

    def test_interrupted_run_writes_an_incomplete_summary(self) -> None:
        runner = load_runner()

        def fake_run(command, cwd):  # noqa: ANN001, ANN202
            raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "r"
            with (
                mock.patch.object(runner.subprocess, "run", fake_run),
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaises(KeyboardInterrupt),
            ):
                runner.main(["--results-dir", str(results)])
            summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "INCOMPLETE")
        self.assertEqual(len(summary["not_run"]), len(runner.SUITES))

    def test_suite_names_are_unique_and_list_is_unchanged(self) -> None:
        runner = load_runner()
        names = [runner.suite_name(s) for s in runner.SUITES]
        self.assertEqual(len(names), len(set(names)))
        listed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_offline_tests.py"), "--list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotIn("junit", listed.stdout)


if __name__ == "__main__":
    unittest.main()
