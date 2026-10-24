#!/usr/bin/env python3
"""run_offline_tests.py - Run every offline suite behind ``make test`` (#437).

The suite list below is the single source of truth for ``make test`` (and its
``make test-offline`` alias). Each suite runs in its own process, in this order,
from the repository root, so recipe modules with the same name never meet in one
interpreter. ``python`` in a suite is replaced by the interpreter running this
script (``make test PYTHON=...``). The run stops at the first failing suite and
exits 1, as the former one-command-per-line Make recipe did.

Each run also writes ``test-results/test/`` (gitignored, removed by ``make clean``, #461):
one JUnit file per suite under ``junit/`` (pytest ``--junitxml``; the unittest suites run
through ``scripts/unittest_junit.py``, which writes the same shape), and a versioned
``summary.json`` aggregated by ``scripts/report_results.py``, with the same one-line
summary printed at the end. A shell-script suite has no JUnit file and counts as one
check. Coverage is not measured, so no ``coverage.xml`` is written. The suite commands
shown by ``--list`` are the plain ones; the JUnit options are added when running.

None of these suites needs a database or Docker. ``--list`` prints the commands
without running them.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
DEFAULT_RESULTS = Path("test-results") / "test"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import report_results  # noqa: E402


def _unittest(pattern: str) -> tuple[str, ...]:
    return ("python", "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v")


SUITES: tuple[tuple[str, ...], ...] = (
    _unittest("test_mcp_smoke.py"),
    _unittest("test_check_expected_coverage.py"),
    _unittest("test_example_requirements.py"),
    (
        "python",
        "-m",
        "pytest",
        "quickstart/5min-fastapi/tests",
        "-q",
        "--ignore=quickstart/5min-fastapi/tests/test_live.py",
    ),
    ("python", "-m", "pytest", "tests/test_ai_agent_offline.py", "-q"),
    ("python", "-m", "pytest", "tests/test_agent_review_gate.py", "-q"),
    ("python", "-m", "pytest", "tests/test_agent_eval.py", "-q"),
    _unittest("test_release*.py"),
    _unittest("test_make_commands.py"),
    _unittest("test_wait_for_cubrid.py"),
    _unittest("test_support_matrix_counts.py"),
    _unittest("test_dependency_floors.py"),
    _unittest("test_dependabot_config.py"),
    _unittest("test_third_party_licenses.py"),
    _unittest("test_pr_title.py"),
    _unittest("test_ci_scope.py"),
    _unittest("test_workflow_timeouts.py"),
    _unittest("test_workflow_installs.py"),
    _unittest("test_workflow_permissions.py"),
    _unittest("test_template_timestamps.py"),
    _unittest("test_table_prefix.py"),
    _unittest("test_quickstart_config.py"),
    _unittest("test_quickstart_cleanup.py"),
    _unittest("test_live_gate.py"),
    _unittest("test_report_results.py"),
    # Before/after checks for scripts/normalize_output.sh (also `make test-normalize`).
    ("bash", "scripts/test_normalize_output.sh"),
)


def commands(python: str = sys.executable) -> list[list[str]]:
    """Every suite as an argv, with ``python`` replaced by ``python``."""
    return [[python if arg == "python" else arg for arg in suite] for suite in SUITES]


def suite_name(suite: tuple[str, ...]) -> str:
    """A short, stable name: ``unittest:<pattern>``, ``pytest:<first path>``, ``bash:<script>``."""
    if suite[1:3] == ("-m", "unittest"):
        return f"unittest:{suite[suite.index('-p') + 1]}"
    if suite[1:3] == ("-m", "pytest"):
        return f"pytest:{suite[3]}"
    return f"{Path(suite[0]).name}:{suite[1]}"


def with_junit(command: list[str], suite: tuple[str, ...], junit: Path) -> list[str] | None:
    """The command with JUnit output added, or None for a suite that cannot write one."""
    if suite[1:3] == ("-m", "unittest"):
        return [command[0], str(SCRIPTS / "unittest_junit.py"), str(junit), *command[3:]]
    if suite[1:3] == ("-m", "pytest"):
        return [*command, f"--junitxml={junit}"]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the commands, run nothing")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=ROOT / DEFAULT_RESULTS,
        help=f"where JUnit files and summary.json go (default: {DEFAULT_RESULTS})",
    )
    args = parser.parse_args(argv)
    if not args.list:
        report_results.reset_results_dir(args.results_dir, ROOT)
    results = args.results_dir.resolve()
    entries: list[dict] = []
    not_run: list[str] = [suite_name(suite) for suite in SUITES]
    failed = False

    def finish() -> None:
        summary = report_results.build_summary("test", entries, not_run)
        path = report_results.write_summary(results, summary)
        print(report_results.console_line(summary, path), flush=True)

    try:
        for number, (suite, command) in enumerate(zip(SUITES, commands()), start=1):
            print(shlex.join(command), flush=True)
            if args.list:
                continue
            name = suite_name(suite)
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
            junit = results / "junit" / f"{number:02d}-{slug}.xml"
            runnable = with_junit(command, suite, junit) or command
            code = subprocess.run(runnable, cwd=ROOT).returncode
            not_run.remove(name)
            entries.append(
                report_results.suite_entry(
                    name, suite, code, junit if runnable is not command else None, results
                )
            )
            if code != 0:
                print(f"make test: FAILED (exit {code}): {shlex.join(command)}", file=sys.stderr)
                failed = True
                break
    except BaseException:
        if not args.list:
            finish()
        raise
    if args.list:
        return 0
    finish()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
