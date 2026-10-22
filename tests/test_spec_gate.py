"""Offline checks for the spec 08-10 evidence lane's fail-closed rules (#421).

No database is used: pytest is replaced by a stub interpreter that writes a
chosen JUnit report, and the live probe is patched.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("spec_gate", ROOT / "scripts" / "spec_gate.py")
spec_gate = importlib.util.module_from_spec(SPEC)
sys.modules["spec_gate"] = spec_gate  # dataclasses resolve annotations through it
SPEC.loader.exec_module(spec_gate)

LIVE = "cubrid+pycubrid://dba@localhost:33000/testdb"
DASHBOARD = "cubrid+pycubrid://dba@localhost:33004/testdb"


def junit(tests: int, skipped: int = 0, failures: int = 0) -> str:
    cases = "".join(
        f'<testcase classname="t" name="c{i}">'
        + ("<skipped/>" if i < skipped else "")
        + ("<failure/>" if skipped <= i < skipped + failures else "")
        + "</testcase>"
        for i in range(tests)
    )
    return (
        f'<testsuites><testsuite tests="{tests}" skipped="{skipped}" '
        f'failures="{failures}" errors="0">{cases}</testsuite></testsuites>'
    )


def result(**counts: int) -> object:
    outcome = spec_gate.SuiteResult("templates/x/tests", "live", ["pytest"], returncode=0)
    for key, value in counts.items():
        setattr(outcome, key, value)
    return outcome


class JudgeTests(unittest.TestCase):
    def test_skips_fail_under_the_gate_and_are_incomplete_without_it(self) -> None:
        gated = result(tests=3, passed=2, skipped=1)
        spec_gate.judge(gated, True, "database: live CUBRID (x)", False)
        self.assertEqual(gated.status, "failed")
        ungated = result(tests=3, passed=2, skipped=1)
        spec_gate.judge(ungated, False, "", False)
        self.assertEqual(ungated.status, "incomplete")
        self.assertEqual(spec_gate.spec_status([ungated], [], False), "INCOMPLETE")

    def test_zero_tests_and_nonzero_exit_fail_even_without_the_gate(self) -> None:
        empty = result(tests=0)
        spec_gate.judge(empty, False, "", False)
        self.assertEqual(empty.status, "failed")
        crashed = result(tests=1, passed=1, returncode=1)
        spec_gate.judge(crashed, False, "", False)
        self.assertEqual(crashed.status, "failed")

    def test_gate_requires_the_live_header_where_the_suite_prints_one(self) -> None:
        fallback = result(tests=1, passed=1)
        spec_gate.judge(fallback, True, "database: in-memory SQLite fallback", True)
        self.assertEqual(fallback.status, "failed")
        # The header must start a line and carry the URL, not merely be mentioned.
        quoted = result(tests=1, passed=1)
        spec_gate.judge(quoted, True, "note: set database: live CUBRID (x)", True)
        self.assertEqual(quoted.status, "failed")
        live = result(tests=1, passed=1)
        spec_gate.judge(live, True, "rootdir: x\ndatabase: live CUBRID (cubrid+pycubrid://)", True)
        self.assertEqual(live.status, "passed")
        self.assertEqual(spec_gate.spec_status([live], [], True), "PASS")

    def test_only_a_gated_run_can_pass(self) -> None:
        live = result(tests=1, passed=1)
        spec_gate.judge(live, False, "", False)
        self.assertEqual(live.status, "passed")
        self.assertEqual(spec_gate.spec_status([live], [], False), "INCOMPLETE")

    def test_preflight_failure_or_no_suite_never_passes(self) -> None:
        self.assertEqual(spec_gate.spec_status([], [], True), "FAIL")
        live = result(tests=1, passed=1, status="passed")
        self.assertEqual(spec_gate.spec_status([live], ["no URL"], True), "FAIL")


class JunitTests(unittest.TestCase):
    def test_counts_and_case_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.xml"
            path.write_text(junit(4, skipped=1, failures=1), encoding="utf-8")
            counts = spec_gate.parse_junit(path)
        self.assertEqual(
            (counts["tests"], counts["passed"], counts["skipped"], counts["failures"]),
            (4, 2, 1, 1),
        )
        self.assertEqual(
            [case["outcome"] for case in counts["cases"]],
            ["skipped", "failed", "passed", "passed"],
        )

    def test_missing_or_malformed_report_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                spec_gate.parse_junit(Path(tmp) / "absent.xml")
            broken = Path(tmp) / "broken.xml"
            broken.write_text("<testsuites>", encoding="utf-8")
            with self.assertRaises(ValueError):
                spec_gate.parse_junit(broken)


class PreflightTests(unittest.TestCase):
    def test_missing_and_non_cubrid_urls_fail_only_under_the_gate(self) -> None:
        self.assertTrue(spec_gate.preflight({"live"}, None, None, True))
        self.assertTrue(spec_gate.preflight({"live"}, "sqlite:///x.db", None, True))
        self.assertTrue(spec_gate.preflight({"live"}, "cubrid://dba@h/testdb", None, True))
        self.assertEqual(spec_gate.preflight({"live"}, LIVE, None, True), [])
        self.assertEqual(spec_gate.preflight({"live"}, None, None, False), [])
        self.assertEqual(spec_gate.preflight({"sqlite"}, None, None, True), [])

    def test_dashboard_needs_its_own_isolated_database(self) -> None:
        self.assertTrue(spec_gate.preflight({"dashboard"}, LIVE, None, True))
        self.assertTrue(spec_gate.preflight({"dashboard"}, LIVE, "sqlite:///d.db", True))
        same = "cubrid+pycubrid://dba@127.0.0.1:33000/TESTDB"
        reasons = spec_gate.preflight({"dashboard"}, LIVE, same, True)
        self.assertTrue(any("isolated" in reason for reason in reasons), reasons)
        self.assertEqual(spec_gate.preflight({"dashboard"}, LIVE, DASHBOARD, True), [])
        self.assertEqual(spec_gate.preflight({"dashboard"}, None, DASHBOARD, True), [])

    def test_suites_get_only_their_own_database_url(self) -> None:
        env = spec_gate.suite_env
        with mock.patch.dict(os.environ, {spec_gate.LIVE_URL_ENV: "inherited"}):
            self.assertEqual(env("live", LIVE, DASHBOARD, True)["CUBRID_TEST_URL"], LIVE)
            self.assertEqual(env("dashboard", LIVE, DASHBOARD, True)["CUBRID_TEST_URL"], DASHBOARD)
            # No dashboard URL: the suite keeps its own SQLite fallback, never the shared DB.
            self.assertNotIn("CUBRID_TEST_URL", env("dashboard", LIVE, None, False))
            self.assertNotIn("CUBRID_TEST_URL", env("sqlite", LIVE, DASHBOARD, True))

    def test_gate_drops_ambient_pytest_options(self) -> None:
        ambient = {"PYTEST_ADDOPTS": "-k nothing", "PYTEST_PLUGINS": "skipper"}
        with mock.patch.dict(os.environ, ambient):
            gated = spec_gate.suite_env("live", LIVE, None, True)
            ungated = spec_gate.suite_env("live", LIVE, None, False)
        self.assertNotIn("PYTEST_ADDOPTS", gated)
        self.assertNotIn("PYTEST_PLUGINS", gated)
        self.assertEqual(ungated["PYTEST_ADDOPTS"], "-k nothing")

    def test_gate_flag_and_strict_environment_values(self) -> None:
        self.assertTrue(spec_gate.gate_enabled(True, {}))
        for value in ("1", "true", "YES", " on "):
            self.assertTrue(spec_gate.gate_enabled(False, {"CUBRID_SPEC_GATE": value}), value)
        for value in ("", "0", "false", "No", "off"):
            self.assertFalse(spec_gate.gate_enabled(False, {"CUBRID_SPEC_GATE": value}), value)
        self.assertFalse(spec_gate.gate_enabled(False, {}))
        for value in ("2", "enabled", "ture"):
            with self.assertRaises(ValueError):
                spec_gate.gate_enabled(True, {"CUBRID_SPEC_GATE": value})

    def test_existing_cookbook_tables_refuse_the_baseline(self) -> None:
        self.assertEqual(spec_gate.baseline_reasons("CUBRID_TEST_URL", {"other"}), [])
        reasons = spec_gate.baseline_reasons("CUBRID_TEST_URL", {"cookbook_products", "x"})
        self.assertTrue(reasons and "cookbook_products" in reasons[0] and "empty" in reasons[0])

    def test_table_changes_cover_created_and_dropped_tables(self) -> None:
        self.assertEqual(spec_gate.table_change_reasons({"a"}, {"a"}), [])
        created, dropped = spec_gate.table_change_reasons({"a", "gone"}, {"a", "new"})
        self.assertIn("'new'", created)
        self.assertIn("dropped pre-existing tables: ['gone']", dropped)


class ManifestTests(unittest.TestCase):
    def test_every_glob_matches_and_reuses_existing_suites_once(self) -> None:
        seen: list[str] = []
        for spec in spec_gate.MANIFEST:
            for suite in spec_gate.expand_suites(spec):
                self.assertTrue((ROOT / suite["path"]).is_dir(), suite["path"])
                self.assertIn(suite["database"], {"live", "dashboard", "sqlite"})
                seen.append(suite["path"])
        self.assertEqual(len(seen), len(set(seen)))
        self.assertIn("templates/dashboard/tests", seen)
        self.assertIn("templates/async-worker/tests", seen)
        self.assertIn("templates/django/tests", seen)
        self.assertFalse(any(path.startswith("quickstart/") for path in seen))
        dashboard = [s for s in spec_gate.expand_suites("spec-10")]
        self.assertEqual([s["database"] for s in dashboard], ["dashboard"])

    def test_unmatched_glob_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                spec_gate.expand_suites("spec-09", Path(tmp))


STUB = textwrap.dedent(
    """
    import os, sys
    if sys.argv[1:2] == ["-c"]:  # the runner's version query
        exec(sys.argv[2])
        sys.exit(0)
    report = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--junitxml="))
    os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
    open(report, "w").write(os.environ["STUB_JUNIT"])
    print("database: live CUBRID (stub)")
    sys.exit(int(os.environ.get("STUB_EXIT", "0")))
    """
)


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.stub = self.tmp / "stub_python.py"
        self.stub.write_text(STUB, encoding="utf-8")
        self.python = self.tmp / "python"
        # A fake interpreter: the stub receives pytest's argv, including --junitxml.
        self.python.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{self.stub}" "$@"\n', encoding="utf-8"
        )
        self.python.chmod(0o755)

    def run_gate(self, env: dict[str, str], *specs: str, gate: bool = True) -> int:
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in {"CUBRID_TEST_URL", "CUBRID_DASHBOARD_TEST_URL", "CUBRID_SPEC_GATE"}
        }
        argv = [*specs, "--evidence-dir", str(self.tmp / "evidence"), "--python", str(self.python)]
        with (
            mock.patch.dict(os.environ, {**clean, **env}, clear=True),
            mock.patch.object(spec_gate, "probe", return_value=("11.2.9.0866", set(), None)),
            mock.patch("sys.stdout"),
        ):
            return spec_gate.main([*argv, *(["--gate"] if gate else [])])

    def summary(self, spec: str) -> dict:
        return json.loads((self.tmp / "evidence" / spec / "summary.json").read_text("utf-8"))

    def test_gate_without_a_database_fails_before_running_pytest(self) -> None:
        self.assertEqual(self.run_gate({"STUB_JUNIT": junit(1)}, "spec-09"), 1)
        summary = self.summary("spec-09")
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["suites"], [])
        self.assertTrue(summary["preflight_failures"])

    def test_gate_rejects_a_sqlite_url(self) -> None:
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": "sqlite:///fallback.db"}
        self.assertEqual(self.run_gate(env, "spec-09"), 1)

    def test_gate_rejects_spec_10_without_an_isolated_dashboard_url(self) -> None:
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "spec-10"), 1)

    def test_skipped_tests_fail_the_gate_but_not_an_ungated_run(self) -> None:
        env = {"STUB_JUNIT": junit(2, skipped=1), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "spec-09"), 1)
        self.assertEqual(self.summary("spec-09")["status"], "FAIL")
        self.assertEqual(self.run_gate(env, "spec-09", gate=False), 0)
        self.assertEqual(self.summary("spec-09")["status"], "INCOMPLETE")

    def test_ungated_all_passed_run_is_incomplete(self) -> None:
        env = {"STUB_JUNIT": junit(2), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "spec-09", gate=False), 0)
        summary = self.summary("spec-09")
        self.assertEqual(summary["status"], "INCOMPLETE")
        self.assertTrue(all(s["status"] == "passed" for s in summary["suites"]))

    def test_invalid_gate_value_is_a_usage_error(self) -> None:
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            self.run_gate({"CUBRID_SPEC_GATE": "maybe", "CUBRID_TEST_URL": LIVE}, "spec-09")
        self.assertEqual(raised.exception.code, 2)

    def test_other_specs_evidence_is_kept(self) -> None:
        evidence = self.tmp / "evidence"
        (evidence / "spec-09").mkdir(parents=True)
        (evidence / "spec-09" / "stale.xml").write_text("old", encoding="utf-8")
        (evidence / "spec-03.xml").write_text("<testsuites/>", encoding="utf-8")
        (evidence / "spec-08").mkdir()
        (evidence / "spec-08" / "summary.json").write_text("{}", encoding="utf-8")
        self.run_gate({"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}, "spec-09")
        self.assertFalse((evidence / "spec-09" / "stale.xml").exists())
        self.assertTrue((evidence / "spec-03.xml").is_file())
        self.assertTrue((evidence / "spec-08" / "summary.json").is_file())

    def test_zero_collected_tests_fail(self) -> None:
        env = {"STUB_JUNIT": junit(0), "STUB_EXIT": "5", "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "spec-09"), 1)

    def test_passing_gate_writes_grouped_evidence(self) -> None:
        env = {
            "STUB_JUNIT": junit(2),
            "CUBRID_TEST_URL": LIVE,
            "CUBRID_DASHBOARD_TEST_URL": DASHBOARD,
        }
        self.assertEqual(self.run_gate(env, "spec-09", "spec-10"), 0)
        for spec in ("spec-09", "spec-10"):
            summary = self.summary(spec)
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["gate"])
            self.assertIn("sha", summary["git"])
            self.assertIn("pycubrid", summary["packages"])
            self.assertTrue(summary["python"]["version"])
            self.assertTrue(all(s["status"] == "passed" for s in summary["suites"]))
            self.assertTrue((self.tmp / "evidence" / spec / "summary.txt").is_file())
        self.assertEqual(self.summary("spec-10")["servers"]["dashboard"]["version"], "11.2.9.0866")
        worker = self.summary("spec-09")["suites"][1]
        self.assertIn("without a Redis broker", worker["note"])

    def run_with_probes(self, *snapshots: set[str]) -> int:
        """Gate spec-09 with successive probe table snapshots (preflight, then before/after)."""
        probes = iter([("11.2", tables, None) for tables in snapshots])
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}
        argv = ["spec-09", "--gate", "--evidence-dir", str(self.tmp / "evidence")]
        with (
            mock.patch.object(spec_gate, "probe", side_effect=lambda _url: next(probes)),
            mock.patch.dict(os.environ, env),
            mock.patch("sys.stdout"),
        ):
            return spec_gate.main([*argv, "--python", str(self.python)])

    def test_preexisting_cookbook_tables_refuse_to_start(self) -> None:
        self.assertEqual(self.run_with_probes({"cookbook_products"}), 1)
        summary = self.summary("spec-09")
        self.assertEqual(summary["suites"], [])
        self.assertIn("dedicated, empty database", summary["preflight_failures"][0])

    def test_new_tables_are_blamed_on_the_suite_that_left_them(self) -> None:
        # preflight, django before/after (leaves one), worker before/after (clean).
        left = {"cookbook_left"}
        self.assertEqual(self.run_with_probes(set(), set(), left, left, left), 1)
        django, worker = self.summary("spec-09")["suites"]
        self.assertTrue(any("cookbook_left" in reason for reason in django["reasons"]))
        self.assertEqual(worker["status"], "passed")

    def test_dropped_tables_fail_the_gate(self) -> None:
        kept = {"keep_me"}
        self.assertEqual(self.run_with_probes(kept, kept, set(), set(), set()), 1)
        reasons = self.summary("spec-09")["suites"][0]["reasons"]
        self.assertIn("dropped pre-existing tables: ['keep_me']", reasons)


class WiringTests(unittest.TestCase):
    def test_make_targets_default_to_the_gate_and_run_offline_tests(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("CUBRID_SPEC_GATE ?= 1", makefile)
        for target in ("spec-08", "spec-09", "spec-10", "spec-08-10"):
            self.assertIn(f"\n{target}:", makefile)
        self.assertIn("test_spec_gate.py", makefile.split("\ntest-offline:", 1)[1].split("\n\n")[0])
        self.assertIn(".spec-evidence/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
