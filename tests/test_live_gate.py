"""Offline checks for the live verification runner's fail-closed rules (#416, #421).

No database is used: pytest is replaced by a stub interpreter that writes a
chosen JUnit report, the live probe is patched, and `make verify-goldens` is
replaced by a stub `make`.
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
SPEC = importlib.util.spec_from_file_location("live_gate", ROOT / "scripts" / "live_gate.py")
live_gate = importlib.util.module_from_spec(SPEC)
sys.modules["live_gate"] = live_gate  # dataclasses resolve annotations through it
SPEC.loader.exec_module(live_gate)

LIVE = "cubrid+pycubrid://dba@localhost:33005/testdb"
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
    outcome = live_gate.SuiteResult("templates/x/tests", "live", ["pytest"], returncode=0)
    for key, value in counts.items():
        setattr(outcome, key, value)
    return outcome


class JudgeTests(unittest.TestCase):
    def test_skips_fail_under_the_gate_and_are_incomplete_without_it(self) -> None:
        gated = result(tests=3, passed=2, skipped=1)
        live_gate.judge(gated, True, "database: live CUBRID (x)", False)
        self.assertEqual(gated.status, "failed")
        ungated = result(tests=3, passed=2, skipped=1)
        live_gate.judge(ungated, False, "", False)
        self.assertEqual(ungated.status, "incomplete")
        self.assertEqual(live_gate.lane_status([ungated], [], False), "INCOMPLETE")

    def test_zero_tests_and_nonzero_exit_fail_even_without_the_gate(self) -> None:
        empty = result(tests=0)
        live_gate.judge(empty, False, "", False)
        self.assertEqual(empty.status, "failed")
        crashed = result(tests=1, passed=1, returncode=1)
        live_gate.judge(crashed, False, "", False)
        self.assertEqual(crashed.status, "failed")

    def test_gate_requires_the_live_header_where_the_suite_prints_one(self) -> None:
        fallback = result(tests=1, passed=1)
        live_gate.judge(fallback, True, "database: in-memory SQLite fallback", True)
        self.assertEqual(fallback.status, "failed")
        # The header must start a line and carry the URL, not merely be mentioned.
        quoted = result(tests=1, passed=1)
        live_gate.judge(quoted, True, "note: set database: live CUBRID (x)", True)
        self.assertEqual(quoted.status, "failed")
        live = result(tests=1, passed=1)
        live_gate.judge(live, True, "rootdir: x\ndatabase: live CUBRID (cubrid+pycubrid://)", True)
        self.assertEqual(live.status, "passed")
        self.assertEqual(live_gate.lane_status([live], [], True), "PASS")

    def test_only_a_gated_run_can_pass(self) -> None:
        live = result(tests=1, passed=1)
        live_gate.judge(live, False, "", False)
        self.assertEqual(live.status, "passed")
        self.assertEqual(live_gate.lane_status([live], [], False), "INCOMPLETE")

    def test_preflight_failure_or_no_suite_never_passes(self) -> None:
        self.assertEqual(live_gate.lane_status([], [], True), "FAIL")
        live = result(tests=1, passed=1, status="passed")
        self.assertEqual(live_gate.lane_status([live], ["no URL"], True), "FAIL")


class JunitTests(unittest.TestCase):
    def test_counts_and_case_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.xml"
            path.write_text(junit(4, skipped=1, failures=1), encoding="utf-8")
            counts = live_gate.parse_junit(path)
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
                live_gate.parse_junit(Path(tmp) / "absent.xml")
            broken = Path(tmp) / "broken.xml"
            broken.write_text("<testsuites>", encoding="utf-8")
            with self.assertRaises(ValueError):
                live_gate.parse_junit(broken)


class PreflightTests(unittest.TestCase):
    def test_missing_and_non_cubrid_urls_fail_only_under_the_gate(self) -> None:
        self.assertTrue(live_gate.preflight({"live"}, None, None, True))
        self.assertTrue(live_gate.preflight({"live"}, "sqlite:///x.db", None, True))
        self.assertTrue(live_gate.preflight({"live"}, "cubrid://dba@h/testdb", None, True))
        self.assertEqual(live_gate.preflight({"live"}, LIVE, None, True), [])
        self.assertEqual(live_gate.preflight({"live"}, None, None, False), [])
        self.assertEqual(live_gate.preflight({"sqlite"}, None, None, True), [])

    def test_dashboard_needs_its_own_isolated_database(self) -> None:
        self.assertTrue(live_gate.preflight({"dashboard"}, LIVE, None, True))
        self.assertTrue(live_gate.preflight({"dashboard"}, LIVE, "sqlite:///d.db", True))
        same = "cubrid+pycubrid://dba@127.0.0.1:33005/TESTDB"
        reasons = live_gate.preflight({"dashboard"}, LIVE, same, True)
        self.assertTrue(any("isolated" in reason for reason in reasons), reasons)
        self.assertEqual(live_gate.preflight({"dashboard"}, LIVE, DASHBOARD, True), [])
        self.assertEqual(live_gate.preflight({"dashboard"}, None, DASHBOARD, True), [])

    def test_dedicated_urls_must_not_name_the_examples_database(self) -> None:
        examples = "cubrid+pycubrid://dba@127.0.0.1:33000/TestDB"
        for needs, live, dashboard in (({"live"}, examples, None), ({"dashboard"}, None, examples)):
            reasons = live_gate.preflight(needs, live, dashboard, True)
            self.assertTrue(any("examples database" in r for r in reasons), reasons)
        self.assertEqual(live_gate.preflight({"examples"}, None, None, True), [])

    def test_suites_get_only_their_own_database_url(self) -> None:
        env = live_gate.suite_env
        with mock.patch.dict(os.environ, {live_gate.LIVE_URL_ENV: "inherited"}):
            self.assertEqual(env("live", LIVE, DASHBOARD, True)["CUBRID_TEST_URL"], LIVE)
            self.assertEqual(env("dashboard", LIVE, DASHBOARD, True)["CUBRID_TEST_URL"], DASHBOARD)
            # No dashboard URL: the suite keeps its own SQLite fallback, never the shared DB.
            self.assertNotIn("CUBRID_TEST_URL", env("dashboard", LIVE, None, False))
            self.assertNotIn("CUBRID_TEST_URL", env("sqlite", LIVE, DASHBOARD, True))
            examples = env("examples", LIVE, DASHBOARD, True)["CUBRID_TEST_URL"]
            self.assertEqual(examples, live_gate.EXAMPLES_URL)

    def test_suites_see_the_gate_as_exactly_one_or_zero(self) -> None:
        with mock.patch.dict(os.environ, {live_gate.GATE_ENV: "yes"}):
            self.assertEqual(live_gate.suite_env("live", LIVE, None, True)["CUBRID_LIVE_GATE"], "1")
            self.assertEqual(
                live_gate.suite_env("live", LIVE, None, False)["CUBRID_LIVE_GATE"], "0"
            )

    def test_gate_drops_ambient_pytest_options(self) -> None:
        ambient = {"PYTEST_ADDOPTS": "-k nothing", "PYTEST_PLUGINS": "skipper"}
        with mock.patch.dict(os.environ, ambient):
            gated = live_gate.suite_env("live", LIVE, None, True)
            ungated = live_gate.suite_env("live", LIVE, None, False)
        self.assertNotIn("PYTEST_ADDOPTS", gated)
        self.assertNotIn("PYTEST_PLUGINS", gated)
        self.assertEqual(ungated["PYTEST_ADDOPTS"], "-k nothing")

    def test_gate_flag_and_strict_environment_values(self) -> None:
        self.assertTrue(live_gate.gate_enabled(True, {}))
        for value in ("1", "true", "YES", " on "):
            self.assertTrue(live_gate.gate_enabled(False, {"CUBRID_LIVE_GATE": value}), value)
        for value in ("", "0", "false", "No", "off"):
            self.assertFalse(live_gate.gate_enabled(False, {"CUBRID_LIVE_GATE": value}), value)
        self.assertFalse(live_gate.gate_enabled(False, {}))
        for value in ("2", "enabled", "ture"):
            with self.assertRaises(ValueError):
                live_gate.gate_enabled(True, {"CUBRID_LIVE_GATE": value})

    def test_existing_cookbook_tables_refuse_the_baseline(self) -> None:
        self.assertEqual(live_gate.baseline_reasons("CUBRID_TEST_URL", {"other"}), [])
        reasons = live_gate.baseline_reasons("CUBRID_TEST_URL", {"cookbook_products", "x"})
        self.assertTrue(reasons and "cookbook_products" in reasons[0] and "empty" in reasons[0])

    def test_table_changes_cover_created_and_dropped_tables(self) -> None:
        self.assertEqual(live_gate.table_change_reasons({"a"}, {"a"}), [])
        created, dropped = live_gate.table_change_reasons({"a", "gone"}, {"a", "new"})
        self.assertIn("'new'", created)
        self.assertIn("dropped pre-existing tables: ['gone']", dropped)
        self.assertEqual(live_gate.table_change_reasons(set(), {"own"}, ["own"]), [])
        self.assertTrue(live_gate.table_change_reasons({"own"}, set(), ["own"]))


class ManifestTests(unittest.TestCase):
    def test_every_glob_matches_and_reuses_existing_suites_once(self) -> None:
        seen: list[str] = []
        for lane in live_gate.MANIFEST:
            for suite in live_gate.expand_suites(lane):
                self.assertTrue((ROOT / suite["path"]).exists(), suite["path"])
                self.assertIn(suite["database"], {"examples", "live", "dashboard", "sqlite"})
                seen.append(suite["path"])
        self.assertEqual(len(seen), len(set(seen)))
        for path in (
            ".",
            "quickstart/5min-fastapi/tests/test_live.py",
            "tests/test_performance_benchmarks.py",
            "tests/test_ai_agent.py",
            "templates/dashboard/tests",
            "templates/async-worker/tests",
            "templates/django/tests",
        ):
            self.assertIn(path, seen)
        dashboard = [s for s in live_gate.expand_suites("dashboard")]
        self.assertEqual([s["database"] for s in dashboard], ["dashboard"])

    def test_full_order_runs_every_lane_once_goldens_first(self) -> None:
        self.assertEqual(sorted(live_gate.FULL_ORDER), sorted(live_gate.MANIFEST))
        self.assertEqual(live_gate.FULL_ORDER[0], "goldens")
        examples = [
            lane
            for lane in live_gate.FULL_ORDER
            if all(s["database"] == "examples" for s in live_gate.expand_suites(lane))
        ]
        # The examples-database lanes run before the dedicated-database ones.
        self.assertEqual(list(live_gate.FULL_ORDER[: len(examples)]), examples)

    def test_unmatched_glob_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                live_gate.expand_suites("django-celery", Path(tmp))


STUB = textwrap.dedent(
    """
    import os, sys
    if sys.argv[1:2] == ["-c"]:  # the runner's version query
        exec(sys.argv[2])
        sys.exit(0)
    if sys.argv[1].endswith("example_requirements.py"):  # the dependency check
        print("missing: stub", file=sys.stderr)
        sys.exit(int(os.environ.get("STUB_DEPS_EXIT", "0")))
    report = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--junitxml="))
    os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
    open(report, "w").write(os.environ["STUB_JUNIT"])
    print("database: live CUBRID (stub)")
    sys.exit(int(os.environ.get("STUB_EXIT", "0")))
    """
)


class StubRunner(unittest.TestCase):
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

    def run_gate(self, env: dict[str, str], *lanes: str, gate: bool = True) -> int:
        clean = {
            k: v
            for k, v in os.environ.items()
            if k not in {"CUBRID_TEST_URL", "CUBRID_DASHBOARD_TEST_URL", "CUBRID_LIVE_GATE"}
        }
        argv = [*lanes, "--evidence-dir", str(self.tmp / "evidence"), "--python", str(self.python)]
        with (
            mock.patch.dict(os.environ, {**clean, **env}, clear=True),
            mock.patch.object(live_gate, "probe", return_value=("11.2.9.0866", set(), None)),
            mock.patch("sys.stdout"),
        ):
            return live_gate.main([*argv, *(["--gate"] if gate else [])])

    def summary(self, lane: str) -> dict:
        return json.loads((self.tmp / "evidence" / lane / "summary.json").read_text("utf-8"))


class RunnerTests(StubRunner):
    def test_gate_without_a_database_fails_before_running_pytest(self) -> None:
        self.assertEqual(self.run_gate({"STUB_JUNIT": junit(1)}, "django-celery"), 1)
        summary = self.summary("django-celery")
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["suites"], [])
        self.assertTrue(summary["preflight_failures"])

    def test_gate_rejects_a_sqlite_url(self) -> None:
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": "sqlite:///fallback.db"}
        self.assertEqual(self.run_gate(env, "django-celery"), 1)

    def test_gate_rejects_dashboard_without_an_isolated_dashboard_url(self) -> None:
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "dashboard"), 1)

    def test_skipped_tests_fail_the_gate_but_not_an_ungated_run(self) -> None:
        env = {"STUB_JUNIT": junit(2, skipped=1), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "django-celery"), 1)
        self.assertEqual(self.summary("django-celery")["status"], "FAIL")
        self.assertEqual(self.run_gate(env, "django-celery", gate=False), 0)
        self.assertEqual(self.summary("django-celery")["status"], "INCOMPLETE")

    def test_ungated_all_passed_run_is_incomplete(self) -> None:
        env = {"STUB_JUNIT": junit(2), "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "django-celery", gate=False), 0)
        summary = self.summary("django-celery")
        self.assertEqual(summary["status"], "INCOMPLETE")
        self.assertTrue(all(s["status"] == "passed" for s in summary["suites"]))

    def test_invalid_gate_value_is_a_usage_error(self) -> None:
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            self.run_gate({"CUBRID_LIVE_GATE": "maybe", "CUBRID_TEST_URL": LIVE}, "django-celery")
        self.assertEqual(raised.exception.code, 2)

    def test_other_lanes_evidence_is_kept(self) -> None:
        evidence = self.tmp / "evidence"
        (evidence / "django-celery").mkdir(parents=True)
        (evidence / "django-celery" / "stale.xml").write_text("old", encoding="utf-8")
        (evidence / "verify-summary.json").write_text("{}", encoding="utf-8")
        (evidence / "web").mkdir()
        (evidence / "web" / "summary.json").write_text("{}", encoding="utf-8")
        self.run_gate({"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}, "django-celery")
        self.assertFalse((evidence / "django-celery" / "stale.xml").exists())
        self.assertTrue((evidence / "verify-summary.json").is_file())
        self.assertTrue((evidence / "web" / "summary.json").is_file())

    def test_zero_collected_tests_fail(self) -> None:
        env = {"STUB_JUNIT": junit(0), "STUB_EXIT": "5", "CUBRID_TEST_URL": LIVE}
        self.assertEqual(self.run_gate(env, "django-celery"), 1)

    def test_passing_gate_writes_grouped_evidence(self) -> None:
        env = {
            "STUB_JUNIT": junit(2),
            "CUBRID_TEST_URL": LIVE,
            "CUBRID_DASHBOARD_TEST_URL": DASHBOARD,
        }
        self.assertEqual(self.run_gate(env, "django-celery", "dashboard"), 0)
        for lane in ("django-celery", "dashboard"):
            summary = self.summary(lane)
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["gate"])
            self.assertIn("sha", summary["git"])
            self.assertIn("pycubrid", summary["packages"])
            self.assertTrue(summary["python"]["version"])
            self.assertTrue(all(s["status"] == "passed" for s in summary["suites"]))
            self.assertTrue((self.tmp / "evidence" / lane / "summary.txt").is_file())
        self.assertEqual(
            self.summary("dashboard")["servers"]["dashboard"]["version"], "11.2.9.0866"
        )
        worker = self.summary("django-celery")["suites"][1]
        self.assertIn("without a Redis broker", worker["note"])

    def run_with_probes(self, *snapshots: set[str]) -> int:
        """Gate django-celery with successive probe table snapshots (preflight, then before/after)."""
        probes = iter([("11.2", tables, None) for tables in snapshots])
        env = {"STUB_JUNIT": junit(1), "CUBRID_TEST_URL": LIVE}
        argv = ["django-celery", "--gate", "--evidence-dir", str(self.tmp / "evidence")]
        with (
            mock.patch.object(live_gate, "probe", side_effect=lambda _url: next(probes)),
            mock.patch.dict(os.environ, env),
            mock.patch("sys.stdout"),
        ):
            return live_gate.main([*argv, "--python", str(self.python)])

    def test_preexisting_cookbook_tables_refuse_to_start(self) -> None:
        self.assertEqual(self.run_with_probes({"cookbook_products"}), 1)
        summary = self.summary("django-celery")
        self.assertEqual(summary["suites"], [])
        self.assertIn("dedicated, empty database", summary["preflight_failures"][0])

    def test_new_tables_are_blamed_on_the_suite_that_left_them(self) -> None:
        # preflight, django before/after (leaves one), worker before/after (clean).
        left = {"cookbook_left"}
        self.assertEqual(self.run_with_probes(set(), set(), left, left, left), 1)
        django, worker = self.summary("django-celery")["suites"]
        self.assertTrue(any("cookbook_left" in reason for reason in django["reasons"]))
        self.assertEqual(worker["status"], "passed")

    def test_dropped_tables_fail_the_gate(self) -> None:
        kept = {"keep_me"}
        self.assertEqual(self.run_with_probes(kept, kept, set(), set(), set()), 1)
        reasons = self.summary("django-celery")["suites"][0]["reasons"]
        self.assertIn("dropped pre-existing tables: ['keep_me']", reasons)


FAKE_MAKE = textwrap.dedent(
    """
    import os, sys
    assert not any(a.startswith("VERIFY_RESULTS=") for a in sys.argv)  # env, not a make var
    results = os.environ["VERIFY_RESULTS"]
    with open(results, "a") as out:
        out.write(os.environ.get("STUB_GOLDENS", ""))
    print("Results: stub")
    sys.exit(int(os.environ.get("STUB_MAKE_EXIT", "0")))
    """
)


class FullVerifyTests(StubRunner):
    """`all` (make verify): upfront checks, every lane, separate golden/pytest results."""

    def setUp(self) -> None:
        super().setUp()
        script = self.tmp / "fake_make.py"
        script.write_text(FAKE_MAKE, encoding="utf-8")
        self.make = self.tmp / "make"
        self.make.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        self.make.chmod(0o755)

    def run_all(self, env: dict[str, str]) -> int:
        base = {
            "STUB_JUNIT": junit(1),
            "STUB_GOLDENS": "PASS\tfundamentals/a.py\nPASS\tmigration/b.py\n",
            "CUBRID_TEST_URL": LIVE,
            "CUBRID_DASHBOARD_TEST_URL": DASHBOARD,
        }
        with mock.patch.object(live_gate.shutil, "which", return_value=str(self.make)):
            return self.run_gate({**base, **env}, "all")

    def verify_summary(self) -> dict:
        return json.loads((self.tmp / "evidence" / "verify-summary.json").read_text("utf-8"))

    def test_full_run_reports_goldens_and_pytest_separately(self) -> None:
        self.assertEqual(self.run_all({}), 0)
        summary = self.verify_summary()
        self.assertEqual((summary["scope"], summary["status"]), ("full", "PASS"))
        self.assertEqual(summary["goldens"]["totals"]["passed"], 2)
        self.assertEqual(list(summary["goldens"]["lanes"]), ["goldens"])
        self.assertEqual(list(summary["pytest"]["lanes"]), list(live_gate.FULL_ORDER[1:]))
        self.assertEqual(set(summary["servers"]), {"examples", "live", "dashboard"})
        self.assertIn("sha", summary["git"])
        cases = self.summary("goldens")["suites"][0]["cases"]
        self.assertEqual(cases[0], {"id": "fundamentals/a.py", "outcome": "PASS"})
        # The root FastAPI SQLite startup suite is not counted as live evidence.
        self.assertEqual(summary["pytest"]["non_live_totals"]["tests"], 1)
        live_suites = sum(
            1
            for lane in live_gate.FULL_ORDER[1:]
            for suite in self.summary(lane)["suites"]
            if suite["database"] != "sqlite"
        )
        self.assertEqual(summary["pytest"]["totals"]["tests"], live_suites)

    def test_ungated_full_run_is_incomplete_and_never_succeeds(self) -> None:
        env = {
            "STUB_JUNIT": junit(1),
            "STUB_GOLDENS": "PASS\ta.py\n",
            "CUBRID_TEST_URL": LIVE,
            "CUBRID_DASHBOARD_TEST_URL": DASHBOARD,
        }
        with mock.patch.object(live_gate.shutil, "which", return_value=str(self.make)):
            code = self.run_gate(env, "all", gate=False)
        self.assertEqual(code, live_gate.EXIT_INCOMPLETE)
        self.assertNotEqual(code, 0)
        self.assertEqual(self.verify_summary()["status"], "INCOMPLETE")

    def test_stale_summary_is_removed_before_the_run(self) -> None:
        evidence = self.tmp / "evidence"
        evidence.mkdir()
        for name in ("verify-summary.json", "verify-summary.txt"):
            (evidence / name).write_text("stale PASS", encoding="utf-8")
        with (
            mock.patch.object(live_gate, "missing_dependencies", side_effect=RuntimeError("x")),
            self.assertRaises(RuntimeError),
        ):
            self.run_all({})
        self.assertFalse((evidence / "verify-summary.json").exists())
        self.assertFalse((evidence / "verify-summary.txt").exists())

    def test_a_failed_golden_fails_the_run_and_is_named(self) -> None:
        env = {"STUB_GOLDENS": "PASS\ta.py\nMISMATCH\tb.py\n", "STUB_MAKE_EXIT": "2"}
        self.assertEqual(self.run_all(env), 1)
        summary = self.verify_summary()
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["goldens"]["failures"], [{"id": "b.py", "outcome": "MISMATCH"}])
        self.assertEqual(summary["pytest"]["status"], "PASS")

    def test_no_golden_compared_fails(self) -> None:
        self.assertEqual(self.run_all({"STUB_GOLDENS": ""}), 1)
        self.assertEqual(self.verify_summary()["goldens"]["status"], "FAIL")

    def test_upfront_checks_fail_before_any_lane_runs(self) -> None:
        for env, needle in (
            ({"CUBRID_TEST_URL": ""}, "CUBRID_TEST_URL is not set"),
            ({"CUBRID_DASHBOARD_TEST_URL": "sqlite:///d.db"}, "no SQLite"),
            (
                {"CUBRID_TEST_URL": "cubrid+pycubrid://dba@localhost:33000/testdb"},
                "examples database",
            ),
            ({"STUB_DEPS_EXIT": "1"}, "run make deps"),
        ):
            with self.subTest(needle=needle):
                self.assertEqual(self.run_all(env), 1)
                summary = self.verify_summary()
                self.assertEqual(summary["status"], "FAIL")
                self.assertTrue(any(needle in r for r in summary["preflight_failures"]), summary)
                self.assertEqual(summary["pytest"]["lanes"], {})
                self.assertFalse((self.tmp / "evidence" / "goldens").exists())

    def test_unreachable_examples_database_fails_upfront(self) -> None:
        def probe(url: str):
            if url == live_gate.EXAMPLES_URL:
                return None, None, "OperationalError: refused"
            return "11.2", set(), None

        with mock.patch.object(live_gate, "probe", side_effect=probe):
            env = {"CUBRID_TEST_URL": LIVE, "CUBRID_DASHBOARD_TEST_URL": DASHBOARD}
            with mock.patch.dict(os.environ, env), mock.patch("sys.stdout"):
                code = live_gate.main(
                    [
                        "all",
                        "--gate",
                        "--evidence-dir",
                        str(self.tmp / "evidence"),
                        "--python",
                        str(self.python),
                    ]
                )
        self.assertEqual(code, 1)
        self.assertIn("unreachable", self.verify_summary()["preflight_failures"][0])

    def test_all_cannot_be_combined_with_lanes(self) -> None:
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            live_gate.main(["all", "web"])
        self.assertEqual(raised.exception.code, 2)


class WiringTests(unittest.TestCase):
    def test_make_targets_default_to_the_gate_and_run_offline_tests(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("CUBRID_LIVE_GATE ?= 1", makefile)
        for target in (
            "verify-quickstart",
            "verify-performance",
            "verify-web",
            "verify-django-celery",
            "verify-ai-agent",
            "verify-dashboard",
            "verify-templates",
            "verify-goldens",
        ):
            self.assertIn(f"\n{target}:", makefile)
        self.assertIn("CUBRID_LIVE_GATE=1 $(PYTHON) scripts/live_gate.py --gate all", makefile)
        # make test is one scripts/run_offline_tests.py run, which lists this suite (#437).
        self.assertIn(
            "scripts/run_offline_tests.py", makefile.split("\ntest:", 1)[1].split("\n\n")[0]
        )
        self.assertIn(
            '_unittest("test_live_gate.py")',
            (ROOT / "scripts/run_offline_tests.py").read_text(encoding="utf-8"),
        )
        self.assertIn(".live-evidence/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
