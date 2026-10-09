"""Offline checks for scripts/check_dependency_floors.py (#152)."""

from __future__ import annotations

import doctest
import importlib.util
import re
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_dependency_floors", ROOT / "scripts/check_dependency_floors.py"
)
floors = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(floors)
MATRIX = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
LANE_SPEC = importlib.util.spec_from_file_location(
    "driver_floors", ROOT / "scripts/driver_floors.py"
)
lane = importlib.util.module_from_spec(LANE_SPEC)
LANE_SPEC.loader.exec_module(lane)
sys.path.insert(0, str(ROOT / "scripts"))
import ci_scope  # noqa: E402

CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class DependencyFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for src in ("fundamentals", "migration", "pitfalls", "quickstart", "templates"):
            shutil.copytree(ROOT / src, self.tmp / src, ignore=shutil.ignore_patterns("*.pyc"))

    def test_repository_matches_documented_contract(self) -> None:
        self.assertEqual(floors.check(ROOT, MATRIX), [])

    def test_bare_driver_requirement_is_rejected(self) -> None:
        target = self.tmp / "quickstart/5min-sqlalchemy/requirements.txt"
        target.write_text("pycubrid\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("no version floor" in e and "pycubrid" in e for e in errors), errors)

    def test_below_global_floor_is_rejected(self) -> None:
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=0.5\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )

    def test_undocumented_custom_floor_is_rejected(self) -> None:
        # A higher, undocumented pin is drift too -- it must be added as an
        # exception (and documented in SUPPORT_MATRIX.md), not pinned ad hoc.
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=1.9\nsqlalchemy-cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )

    def test_global_floor_rejects_an_unexpected_upper_bound(self) -> None:
        # The documented global floor is one-sided (>=X.Y, no ceiling); a
        # correct-looking lower bound with a smuggled upper bound is still
        # drift from the documented contract.
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid>=1.6.1,<1.7\nsqlalchemy-cubrid>=1.0,<1.1\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )
        self.assertTrue(
            any(
                "expected sqlalchemy-cubrid>=1.0, no upper bound (global floor)" in e
                for e in errors
            ),
            errors,
        )

    def test_advanced_sqlalchemy_floor_rejects_an_unexpected_upper_bound(self) -> None:
        target = self.tmp / "fundamentals/pandas/requirements.txt"
        text = target.read_text().replace(
            "sqlalchemy-cubrid>=1.4.2", "sqlalchemy-cubrid>=1.4.2,<1.5"
        )
        self.assertIn("<1.5", text)
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any(
                "expected sqlalchemy-cubrid>=1.4.2, no upper bound (advanced SQLAlchemy floor)" in e
                for e in errors
            ),
            errors,
        )

    def test_template_exception_wrong_floor_is_rejected(self) -> None:
        target = self.tmp / "templates/flask/requirements.txt"
        text = target.read_text().replace("pycubrid>=1.7,<2", "pycubrid>=1.6.1")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.7,<2 (template floor)" in e for e in errors), errors
        )

    def test_fundamentals_pycubrid_exact_floor_is_enforced(self) -> None:
        target = self.tmp / "fundamentals/pycubrid/requirements.txt"
        target.write_text("pycubrid>=1.7,<2\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected pycubrid>=1.9,<2" in e for e in errors), errors)

    def test_fundamentals_sqlalchemy_collection_floors_are_enforced(self) -> None:
        target = self.tmp / "fundamentals/sqlalchemy/requirements.txt"
        target.write_text("sqlalchemy>=2.0\npycubrid>=1.8,<2\nsqlalchemy-cubrid>=1.4.2\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected pycubrid>=1.9,<2" in e for e in errors), errors)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.9 in" in e for e in errors), errors)

    def test_fundamentals_alembic_exact_sqlalchemy_floor_is_enforced(self) -> None:
        target = self.tmp / "fundamentals/alembic/requirements.txt"
        text = target.read_text().replace("sqlalchemy-cubrid>=1.8", "sqlalchemy-cubrid>=1.0")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.8 in" in e for e in errors), errors)

    def test_fundamentals_alembic_rejects_sqlalchemy_floor_above_exact(self) -> None:
        target = self.tmp / "fundamentals/alembic/requirements.txt"
        text = target.read_text().replace("sqlalchemy-cubrid>=1.8", "sqlalchemy-cubrid>=1.9")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.8 in" in e for e in errors), errors)

    def test_stale_alembic_exception_directory_is_reported(self) -> None:
        shutil.rmtree(self.tmp / "fundamentals/alembic")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("fundamentals/alembic" in e and "no longer exists" in e for e in errors), errors
        )

    def test_stale_exception_directory_is_reported(self) -> None:
        shutil.rmtree(self.tmp / "fundamentals/pycubrid")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("fundamentals/pycubrid" in e and "no longer exists" in e for e in errors), errors
        )

    def test_extras_and_spaced_specifiers_are_accepted(self) -> None:
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("pycubrid >= 1.6.1\nsqlalchemy-cubrid[pycubrid]>=1.0\n")
        self.assertEqual(floors.check(self.tmp, MATRIX), [])
        target.write_text("sqlalchemy-cubrid[pycubrid] >= 0.9\npycubrid>=1.6.1\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.0" in e for e in errors), errors)

    def test_driver_names_are_case_and_separator_insensitive(self) -> None:
        target = self.tmp / "migration/java-to-python/requirements.txt"
        target.write_text("PyCUBRID>=1.7,<2\nsqlalchemy_cubrid>=1.0\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(
            any("expected pycubrid>=1.6.1, no upper bound (global floor)" in e for e in errors),
            errors,
        )
        self.assertFalse(any("sqlalchemy-cubrid" in e for e in errors), errors)
        target.write_text("PyCUBRID>=1.6.1\nSQLAlchemy.Cubrid>=0.9\n")
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.0" in e for e in errors), errors)
        self.assertEqual(floors.parse_driver_requirement("pycubrid-extra>=1"), None)

    def test_fundamentals_async_exact_sqlalchemy_floor_is_enforced(self) -> None:
        target = self.tmp / "fundamentals/async/requirements.txt"
        text = target.read_text().replace("sqlalchemy-cubrid>=1.5", "sqlalchemy-cubrid>=1.4.2")
        target.write_text(text)
        errors = floors.check(self.tmp, MATRIX)
        self.assertTrue(any("expected sqlalchemy-cubrid>=1.5 in" in e for e in errors), errors)

    def test_missing_global_floor_in_matrix_is_reported(self) -> None:
        matrix = MATRIX.replace("| pycubrid | ≥ 1.6.1 |", "| pycubrid | removed |")
        errors = floors.check(ROOT, matrix)
        self.assertIn("SUPPORT_MATRIX.md: no global floor found for 'pycubrid'", errors)


def _base(spec: str) -> str:
    return spec.split(",", 1)[0]


class FloorLaneTests(unittest.TestCase):
    """The exact-floor CI lane (#241) stays in sync with the documented floors."""

    def setUp(self) -> None:
        self.plan = lane.plan(ROOT, MATRIX)
        self.dirs = {d: (name, pins) for name, pins, dirs in self.plan for d in dirs}

    def test_every_documented_floor_is_installed_by_the_lane(self) -> None:
        table = dict(
            re.findall(r"^\| (pycubrid|sqlalchemy-cubrid) \| ≥ ([0-9.]+) \|", MATRIX, re.M)
        )
        self.assertEqual(set(table), {"pycubrid", "sqlalchemy-cubrid"})
        documented = {(driver, version) for driver, version in table.items()}
        documented |= {
            ("sqlalchemy-cubrid", floors.ADVANCED_SQLALCHEMY_FLOOR),
            ("pycubrid", _base(floors.TEMPLATE_PYCUBRID_FLOOR)),
            ("sqlalchemy-cubrid", _base(floors.TEMPLATE_SQLALCHEMY_FLOOR)),
        }
        documented |= {("pycubrid", _base(v)) for v in floors.EXACT_PYCUBRID_FLOOR.values()}
        documented |= {
            ("sqlalchemy-cubrid", _base(v)) for v in floors.EXACT_SQLALCHEMY_FLOOR.values()
        }
        documented |= {("pycubrid", v) for v in lane.NO_REQUIREMENTS_FLOORS.values() if v}
        installed = {(d, v) for _, pins, _ in self.plan for d, v in pins.items()}
        self.assertEqual(documented - installed, set())

    def test_async_floor_is_documented_in_the_support_matrix(self) -> None:
        self.assertEqual(self.dirs["fundamentals/async"][1]["sqlalchemy-cubrid"], "1.5")
        flat = " ".join(MATRIX.split())
        self.assertIn("≥ 1.5 for the async `cubrid+aiopycubrid://` recipe", flat)
        self.assertIn("`fundamentals/async` pins `≥ 1.5`", flat)

    def test_directory_without_a_driver_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "d").mkdir()
            (Path(tmp) / "d/requirements.txt").write_text("sqlalchemy>=2.0\n")
            with self.assertRaisesRegex(ValueError, "declares no"):
                lane.directory_floors(Path(tmp), "d", MATRIX)

    def test_unpinned_installed_driver_is_a_problem(self) -> None:
        # sqlalchemy-cubrid pulls in pycubrid; if the set does not pin it, it floats.
        pins = {"sqlalchemy-cubrid": "1.5"}
        self.assertEqual(lane.floor_problems({"sqlalchemy-cubrid": "1.5.0"}, pins), [])
        problems = lane.floor_problems({"sqlalchemy-cubrid": "1.5.0", "pycubrid": "1.9.0"}, pins)
        self.assertEqual(len(problems), 1)
        self.assertIn("pycubrid", problems[0])
        self.assertTrue(lane.floor_problems({}, pins))

    def test_a_failing_set_does_not_stop_the_remaining_sets(self) -> None:
        plan = [
            ("one", {"pycubrid": "1.7"}, ("fundamentals/crud",)),
            ("two", {"pycubrid": "1.7"}, ("fundamentals/crud",)),
        ]
        calls = []

        def install(venv, pins, dirs):
            calls.append(venv.name)
            if venv.name == "one":
                raise subprocess.CalledProcessError(1, ["pip", "install"])
            return Path("python")

        out = io.StringIO()
        with (
            mock.patch.object(lane, "plan", return_value=plan),
            mock.patch.object(lane, "_install", side_effect=install),
            mock.patch.object(lane, "_installed", return_value={"pycubrid": "1.7.0"}),
            mock.patch.object(lane, "_wait_ready"),
            mock.patch.object(lane, "_run_golden", return_value=[]),
            contextlib.redirect_stdout(out),
        ):
            code = lane.run([], Path("work"))
        self.assertEqual(calls, ["one", "two"])
        self.assertEqual(code, 1)
        self.assertRegex(out.getvalue(), r"\| `one` .*FAIL")
        self.assertRegex(out.getvalue(), r"\| `two` .*pass")

    def test_goldens_run_with_a_short_timeout_and_no_stdin(self) -> None:
        self.assertEqual(lane.SCRIPT_TIMEOUT, 60)
        with mock.patch.object(lane.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout=b"")
            lane._run_golden(Path("python"), Path("s.py"), ROOT / "README.md")
        first = run.call_args_list[0].kwargs
        self.assertIs(first["stdin"], subprocess.DEVNULL)
        self.assertEqual(first["timeout"], 60)

    def test_directory_specific_floors_run_on_their_own_directory(self) -> None:
        for label, exact in (
            ("pycubrid", floors.EXACT_PYCUBRID_FLOOR),
            ("sqlalchemy-cubrid", floors.EXACT_SQLALCHEMY_FLOOR),
        ):
            for directory, spec in exact.items():
                with self.subTest(directory=directory, driver=label):
                    self.assertIn(directory, self.dirs)
                    self.assertEqual(self.dirs[directory][1][label], _base(spec))

    def test_global_floor_set_installs_the_support_matrix_table(self) -> None:
        name, pins, _ = self.plan[0]
        self.assertEqual(name, "global")
        self.assertEqual(pins, floors._global_floors(MATRIX))

    def test_golden_directories_without_requirements_are_covered(self) -> None:
        roots = ci_scope.example_roots(ROOT)
        bare = {r for r in roots if not (ROOT / r / "requirements.txt").is_file()}
        self.assertEqual(bare, set(lane.NO_REQUIREMENTS_FLOORS))
        for directory in bare:
            self.assertIn(directory, self.dirs)
        flat = " ".join(MATRIX.split())
        self.assertIn("`fundamentals/lob-handling`, which needs `pycubrid>=1.7`", flat)
        self.assertEqual(lane.NO_REQUIREMENTS_FLOORS["fundamentals/lob-handling"], "1.7")

    def test_lane_pins_follow_the_recipe_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copytree(ROOT / "fundamentals", base / "fundamentals")
            for src in ("migration", "pitfalls", "quickstart"):
                shutil.copytree(ROOT / src, base / src)
            req = base / "fundamentals/pandas/requirements.txt"
            req.write_text(
                req.read_text().replace("sqlalchemy-cubrid>=1.4.2", "sqlalchemy-cubrid>=1.4.3")
            )
            pins = {name: p for name, p, _ in lane.plan(base, MATRIX)}
            self.assertEqual(pins["advanced-sqlalchemy"]["sqlalchemy-cubrid"], "1.4.3")
            # Two directories in one set may not disagree.
            req = base / "fundamentals/connect/requirements.txt"
            req.write_text("pycubrid>=1.8,<2\n")
            with self.assertRaisesRegex(ValueError, "1.7-line"):
                lane.plan(base, MATRIX)

    def test_floor_changes_select_the_lane(self) -> None:
        roots = ci_scope.example_roots(ROOT)
        for directory in self.dirs:
            req = f"{directory}/requirements.txt"
            if (ROOT / req).is_file():
                with self.subTest(path=req):
                    self.assertIn(req, ci_scope.FLOORS)
                    self.assertTrue(ci_scope.classify("pull_request", [req], roots)["floors"])
        for path in (
            "SUPPORT_MATRIX.md",
            "scripts/check_dependency_floors.py",
            "scripts/driver_floors.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(ci_scope.classify("pull_request", [path], roots)["floors"])
        self.assertFalse(ci_scope.classify("pull_request", ["README.md"], roots)["floors"])
        self.assertFalse(ci_scope.classify("push", [], roots)["floors"])
        for event in ("schedule", "workflow_dispatch"):
            self.assertTrue(ci_scope.classify(event, [], roots)["floors"])

    def test_ci_job_runs_the_lane_on_one_cubrid_and_is_gated(self) -> None:
        job = CI.split("\n  driver-floors:\n", 1)[1].split("\n  # ", 1)[0]
        self.assertIn("if: needs.classify.outputs.floors == 'true'", job)
        self.assertIn("run: python scripts/driver_floors.py run", job)
        self.assertEqual(re.findall(r"image: (cubrid/cubrid:\S+)", job), ["cubrid/cubrid:11.4"])
        self.assertIn("persist-credentials: false", job)
        self.assertRegex(job, r"timeout-minutes: \d+")
        gate = CI.split("  ci-gate:\n", 1)[1]
        self.assertIn("driver-floors", gate.split("needs: [", 1)[1].split("]", 1)[0])
        self.assertIn("W_DRIVER_FLOORS: ${{ needs.classify.outputs.floors }}", gate)


def load_tests(loader, tests, pattern):
    tests.addTests(doctest.DocTestSuite(floors))
    tests.addTests(doctest.DocTestSuite(lane))
    return tests


if __name__ == "__main__":
    unittest.main()
