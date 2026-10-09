"""Policy tests for the tiered CI classifier and gate (#222)."""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_scope  # noqa: E402

CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
SMOKE = (ROOT / ".github/workflows/smoke-test.yml").read_text(encoding="utf-8")
ROOTS = ci_scope.example_roots(ROOT)
LIVE = (
    "web",
    "dashboard",
    "async_worker",
    "django",
    "cqrs",
    "compat",
    "smoke_114",
    "smoke_112",
    "floors",
)
CQRS = ci_scope.CQRS_ROOT


def scope(*paths: str, event: str = "pull_request") -> dict[str, object]:
    return ci_scope.classify(event, paths, ROOTS)


def selected(result: dict[str, object]) -> set[str]:
    return {lane for lane in LIVE if result[lane]}


class ClassifierTests(unittest.TestCase):
    def test_example_roots_are_directories_owning_expected(self) -> None:
        self.assertIn("fundamentals/pycubrid", ROOTS)
        self.assertIn("templates/batch-etl", ROOTS)
        self.assertNotIn("templates/flask", ROOTS)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a/b/expected").mkdir(parents=True)
            (base / "c").mkdir()
            (base / "c/expected").write_text("not a directory")
            (base / ".git/x/expected").mkdir(parents=True)
            self.assertEqual(ci_scope.example_roots(base), ["a/b"])

    def test_docs_only_pr_starts_no_live_cubrid(self) -> None:
        result = scope(
            "README.md",
            "docs/README.ko.md",
            "templates/flask/01-basic-crud/README.md",
            "fundamentals/pycubrid/README.md",
            "mkdocs.yml",
        )
        self.assertEqual(result["tier"], "docs")
        self.assertEqual(selected(result), set())
        self.assertEqual(result["verify_paths"], "")

    def test_support_matrix_change_runs_only_the_floor_lane(self) -> None:
        # SUPPORT_MATRIX.md documents the driver floors (#241): docs otherwise.
        result = scope("SUPPORT_MATRIX.md", "README.md")
        self.assertEqual(result["tier"], "pr")
        self.assertEqual(selected(result), {"floors"})
        self.assertEqual(result["verify_paths"], "")

    def test_tooling_pr_runs_only_cheap_checks(self) -> None:
        result = scope("scripts/check_docs_sync.py", "tests/test_docs_sync.py", "pyproject.toml")
        self.assertEqual(result["tier"], "docs")
        self.assertEqual(selected(result), set())

    def test_each_recipe_family_starts_only_its_suite(self) -> None:
        cases = {
            "templates/flask/05-batch-operations/app.py": {"web"},
            "templates/api-service-fastapi/recipes/02-orders/main.py": {"web"},
            "templates/api-service-fastapi/app/main.py": {"web"},
            "templates/api-service-fastapi/tests/test_root_app.py": {"web"},
            "templates/dashboard/03_kpis.py": {"dashboard"},
            "templates/async-worker/tasks/__init__.py": {"async_worker"},
            "templates/django/app/views.py": {"django"},
            f"{CQRS}/app/events.py": {"cqrs"},
        }
        for path, lanes in cases.items():
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(result["tier"], "pr")
                self.assertEqual(selected(result), lanes)
                self.assertEqual(result["cqrs_cubrid"], ["11.4"])

    def test_cqrs_pins_run_both_cubrid_versions(self) -> None:
        result = scope(f"{CQRS}/requirements.txt")
        self.assertEqual(selected(result), {"cqrs"})
        self.assertEqual(result["cqrs_cubrid"], ["11.2", "11.4"])

    def test_golden_example_starts_scoped_11_4_smoke(self) -> None:
        result = scope("templates/batch-etl/02_analysis.py", "fundamentals/json/01_json.py")
        self.assertEqual(selected(result), {"smoke_114"})
        self.assertEqual(result["verify_paths"], "fundamentals/json templates/batch-etl")

    def test_compatibility_surface_adds_python_endpoints(self) -> None:
        result = scope("fundamentals/sqlalchemy/requirements.txt")
        # A floor-lane directory's requirements also re-run the exact floors (#241).
        self.assertEqual(selected(result), {"compat", "smoke_114", "floors"})
        self.assertEqual(result["python"], ["3.11", "3.14"])
        self.assertEqual(result["verify_paths"], "fundamentals/sqlalchemy")

    def test_ai_agent_change_runs_smoke_with_full_verify(self) -> None:
        for path in ("templates/ai-agent/03_rag_metadata.py", "tests/test_ai_agent.py"):
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(selected(result), {"smoke_114"})
                self.assertEqual(result["verify_paths"], ".")

    def test_example_files_without_live_consumer_stay_offline(self) -> None:
        result = scope(
            "performance/bulk-insert/bench.py",
            "quickstart/5min-fastapi/main.py",
            "fundamentals/parameterized-queries/04_parameterized.py",
        )
        self.assertEqual(selected(result), set())

    def test_example_tree_file_outside_golden_roots_fails_closed(self) -> None:
        for path in ("pitfalls/_common.py", "fundamentals/shared.py", "migration/x/helper.py"):
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(selected(result), {"smoke_114"})
                self.assertEqual(result["verify_paths"], ".")

    def test_grouped_dependabot_recipe_bump_selects_only_touched_suites(self) -> None:
        flask = [f"templates/flask/{n:02d}-x/requirements.txt" for n in range(1, 12)]
        result = scope(*flask, "templates/api-service-fastapi/recipes/02-orders/requirements.txt")
        self.assertEqual(selected(result), {"web"})
        result = scope(
            "fundamentals/pandas/requirements.txt", "templates/dashboard/requirements.txt"
        )
        self.assertEqual(selected(result), {"dashboard", "smoke_114", "floors"})
        self.assertEqual(result["verify_paths"], "fundamentals/pandas")

    def test_release_smoke_change_runs_both_smoke_lanes_fully(self) -> None:
        for path in ci_scope.RELEASE_SMOKE:
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(selected(result), {"smoke_114", "smoke_112"})
                self.assertEqual(result["verify_paths"], ".")

    def test_shared_live_infrastructure_fans_out(self) -> None:
        for path in ("Makefile", "scripts/normalize_output.sh", "docker-compose.yml"):
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(result["tier"], "pr")
                self.assertEqual(selected(result), set(LIVE))
                self.assertEqual(result["cqrs_cubrid"], ["11.2", "11.4"])
                self.assertEqual(result["python"], ["3.11", "3.14"])
                self.assertEqual(result["verify_paths"], ".")

    def test_ci_policy_change_runs_every_lane(self) -> None:
        for path in ci_scope.SELF[:1] + (
            "scripts/ci_scope.py",
            ".github/actions/pr-smoke/action.yml",
        ):
            with self.subTest(path=path):
                result = scope(path)
                self.assertEqual(result["tier"], "full")
                self.assertEqual(selected(result), set(LIVE))
                self.assertEqual(result["python"], ["3.11", "3.14"])

    def test_unknown_path_fails_closed(self) -> None:
        for path in ("new-top-level/thing.py", '"quoted\\tpath.py"'):
            with self.subTest(path=path):
                result = scope(path)
                self.assertTrue(
                    {"web", "dashboard", "async_worker", "django", "cqrs", "smoke_114"}
                    <= selected(result)
                )
                self.assertEqual(result["verify_paths"], ".")

    def test_unsafe_example_root_forces_full_verify(self) -> None:
        result = ci_scope.classify("pull_request", ["fundamentals/x y/a.py"], ["fundamentals/x y"])
        self.assertTrue(result["smoke_114"])
        self.assertEqual(result["verify_paths"], ".")

    def test_empty_pr_diff_and_unknown_event_fail_closed(self) -> None:
        self.assertEqual(scope()["tier"], "full")
        self.assertEqual(scope("README.md", event="merge_group")["tier"], "full")

    def test_broad_events_keep_python_and_cqrs_evidence(self) -> None:
        for event in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                result = scope(event=event)
                self.assertEqual(result["tier"], "main")
                self.assertEqual(result["python"], ["3.11", "3.12", "3.13", "3.14"])
                self.assertEqual(result["cqrs_cubrid"], ["11.2", "11.4"])
                floors = {"floors"} if event != "push" else set()
                self.assertEqual(selected(result), {"compat", "cqrs"} | floors)

    def test_render_is_github_output_lines(self) -> None:
        text = ci_scope.render(scope("templates/django/app/views.py"))
        self.assertIn("django=true\n", text)
        self.assertIn('python=["3.12"]\n', text)
        self.assertIn("verify_paths=\n", text)
        self.assertTrue(all("=" in line for line in text.splitlines()))

    def test_main_prints_rendered_scope_from_stdin(self) -> None:
        stdin = io.StringIO("templates/django/app/views.py\nREADME.md\n")
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), contextlib.redirect_stdout(stdout):
            code = ci_scope.main(["--event", "pull_request", "--root", str(ROOT)])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue(), ci_scope.render(scope("templates/django/app/views.py", "README.md"))
        )
        lines = stdout.getvalue().splitlines()
        self.assertIn("tier=pr", lines)
        self.assertIn("django=true", lines)
        self.assertIn("web=false", lines)
        self.assertIn('python=["3.12"]', lines)

    def test_main_requires_event(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ci_scope.main([])


def gate_script() -> str:
    gate = CI.split("  ci-gate:\n", 1)[1]
    return textwrap.dedent(gate.split("        run: |\n", 1)[1])


def gate_env_names(prefix: str) -> list[str]:
    gate = CI.split("  ci-gate:\n", 1)[1]
    return re.findall(rf"^          ({prefix}_[A-Z0-9_]+): \$\{{\{{", gate, re.MULTILINE)


class GateTests(unittest.TestCase):
    def run_gate(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "TIER": "pr"}
        env.update(dict.fromkeys(gate_env_names("R"), "success"))
        env.update(dict.fromkeys(gate_env_names("W"), "true"))
        env.update(overrides)
        return subprocess.run(
            ["bash", "-c", gate_script()], env=env, capture_output=True, text=True, timeout=5
        )

    def test_every_lane_is_in_needs_and_checked(self) -> None:
        gate = CI.split("  ci-gate:\n", 1)[1]
        needs = gate.split("needs: [", 1)[1].split("]", 1)[0].split(", ")
        jobs = re.findall(r"^  ([a-z0-9-]+):\n", CI.split("\njobs:\n", 1)[1], re.MULTILINE)
        self.assertEqual(sorted(needs), sorted(j for j in jobs if j != "ci-gate"))
        loop = gate_script().split("for var in ", 1)[1].split(";", 1)[0].split()
        self.assertEqual(sorted(loop), sorted(gate_env_names("R")))
        for job in needs:
            var = "R_" + job.upper().replace("-", "_")
            self.assertIn(f"{var}: ${{{{ needs.{job}.result }}}}", gate)

    def test_conditional_lanes_use_the_same_output_as_their_if(self) -> None:
        gate = CI.split("  ci-gate:\n", 1)[1]
        for name in gate_env_names("W"):
            output = re.search(rf"{name}: \$\{{\{{ needs\.classify\.outputs\.(\w+) \}}\}}", gate)
            job = name.removeprefix("W_").lower().replace("_", "-")
            body = CI.split(f"  {job}:\n", 1)[1].split("\n  # ", 1)[0]
            with self.subTest(job=job):
                self.assertIsNotNone(output)
                self.assertIn(f"if: needs.classify.outputs.{output[1]} == 'true'", body)
        self.assertEqual(len(gate_env_names("W")), 9)

    def test_classifier_outputs_are_all_exported(self) -> None:
        classify = CI.split("  classify:\n", 1)[1].split("    steps:", 1)[0]
        for key in scope("README.md"):
            self.assertIn(f"{key}: ${{{{ steps.scope.outputs.{key} }}}}", classify)

    def test_all_success_passes(self) -> None:
        self.assertEqual(self.run_gate().returncode, 0)

    def test_skip_passes_only_when_classifier_said_false(self) -> None:
        for wanted, ok in (("false", True), ("true", False), ("", False)):
            with self.subTest(wanted=wanted):
                result = self.run_gate(R_SMOKE_112="skipped", W_SMOKE_112=wanted)
                self.assertEqual(result.returncode == 0, ok, result.stdout)

    def test_failed_or_cancelled_lane_fails_even_when_not_selected(self) -> None:
        for result in ("failure", "cancelled"):
            with self.subTest(result=result):
                check = self.run_gate(R_DASHBOARD_PYTEST=result, W_DASHBOARD_PYTEST="false")
                self.assertNotEqual(check.returncode, 0)

    def test_always_required_jobs_cannot_be_skipped(self) -> None:
        for var in (
            "R_CLASSIFY",
            "R_LINT_PYTHON",
            "R_QUICKSTART_TESTS",
            "R_DOCS_SYNC",
            "R_DOCS_SITE",
        ):
            with self.subTest(var=var):
                self.assertNotEqual(self.run_gate(**{var: "skipped"}).returncode, 0)

    def test_missing_classification_fails(self) -> None:
        overrides = dict.fromkeys(gate_env_names("W"), "")
        overrides.update(dict.fromkeys(gate_env_names("R"), "skipped"))
        overrides.update(R_CLASSIFY="failure", R_LINT_PYTHON="success")
        self.assertNotEqual(self.run_gate(**overrides).returncode, 0)


class WorkflowWiringTests(unittest.TestCase):
    def test_root_fastapi_app_smoke_test_is_wired_with_its_own_requirements(self) -> None:
        # The root app has its own requirements (pydantic-settings is not in the
        # shared lists), so both live lanes must install them and run its suite.
        suite = "templates/api-service-fastapi/tests"
        requirements = "-r templates/api-service-fastapi/requirements.txt"
        pytest_suites = CI[CI.index("  pytest-suites:") : CI.index("  dashboard-pytest:")]
        for name, text in (("ci.yml pytest-suites", pytest_suites), ("smoke-test.yml", SMOKE)):
            with self.subTest(workflow=name):
                self.assertIn(suite, text)
                self.assertIn(requirements, text)
        self.assertTrue(
            (ROOT / "templates/api-service-fastapi/tests/test_root_app.py").is_file(),
        )

    def test_docs_site_build_runs_on_every_pr(self) -> None:
        # A PR that only deletes or renames an example linked from a README
        # classifies as "docs" with no docs path, yet scripts/stage_docs.py must
        # still fail it (#154): the job has no classifier condition.
        result = scope("fundamentals/parameterized-queries/removed_example.py")
        self.assertEqual(result["tier"], "docs")
        self.assertEqual(selected(result), set())
        self.assertNotIn("docs_site", result)
        body = CI.split("  docs-site:\n", 1)[1].split("\n  # ", 1)[0].split("\n\n  ", 1)[0]
        self.assertNotIn("if:", body)
        self.assertNotIn("needs:", body)
        self.assertNotIn("W_DOCS_SITE", CI)
        self.assertIn("      - run: make docs", body)

    def test_required_smoke_check_names_are_plain_ci_jobs(self) -> None:
        for job, version in (("smoke-114", "11.4"), ("smoke-112", "11.2")):
            body = CI.split(f"  {job}:\n", 1)[1].split("\n\n", 1)[0]
            with self.subTest(job=job):
                self.assertIn(f"    name: Smoke Tests (CUBRID {version})\n", body)
                self.assertNotIn("matrix", body)
                self.assertIn("uses: ./.github/actions/pr-smoke", body)
                self.assertIn(f'cubrid-version: "{version}"', body)
                self.assertIn("persist-credentials: false", body)

    def test_pr_smoke_action_runs_goldens_agents_and_mcp(self) -> None:
        action = (ROOT / ".github/actions/pr-smoke/action.yml").read_text(encoding="utf-8")
        self.assertIn('make verify VERIFY_PATHS="$VERIFY_PATHS"', action)
        self.assertIn("VERIFY_PATHS: ${{ inputs.verify-paths }}", action)
        self.assertIn("tests/test_ai_agent.py", action)
        self.assertIn("python scripts/mcp_smoke.py", action)
        self.assertIn("release_smoke.py freeze", action)
        self.assertNotIn("uses:", action)  # no unpinned/unmanaged actions

    def test_smoke_workflow_dropped_only_the_pull_request_trigger(self) -> None:
        triggers = "\n" + SMOKE.split("\non:\n", 1)[1].split("\n# Release verifications", 1)[0]
        self.assertNotIn("  pull_request", triggers)
        for trigger in ("push:", "schedule:", "repository_dispatch:", "workflow_dispatch:"):
            self.assertIn(f"\n  {trigger}", triggers)
        self.assertIn('cron: "0 0 * * *"', triggers)
        call = triggers.split("  workflow_call:\n", 1)[1]
        for name in ("package", "version"):
            block = call.split(f"      {name}:\n", 1)[1].split("\n      ", 1)[0]
            self.assertIn("required: true", call.split(f"      {name}:\n", 1)[1][:300])
            self.assertTrue(block)
        for output in ("status", "requested_version", "installed_version", "artifact"):
            self.assertIn(f"      {output}:\n", call)

    def test_mcp_contract_is_shared(self) -> None:
        self.assertIn("run: python scripts/mcp_smoke.py", SMOKE)
        self.assertNotIn("list_tools", SMOKE)

    def test_ci_owns_broad_python_and_cqrs_events(self) -> None:
        triggers = "\n" + CI.split("\non:\n", 1)[1].split("\nconcurrency:", 1)[0]
        for trigger in ("pull_request:", "push:", "schedule:", "workflow_dispatch:"):
            self.assertIn(f"\n  {trigger}", triggers)


if __name__ == "__main__":
    unittest.main()
