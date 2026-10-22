#!/usr/bin/env python3
"""run_offline_tests.py - Run every offline suite behind ``make test`` (#437).

The suite list below is the single source of truth for ``make test`` (and its
``make test-offline`` alias). Each suite runs in its own process, in this order,
from the repository root, so recipe modules with the same name never meet in one
interpreter. ``python`` in a suite is replaced by the interpreter running this
script (``make test PYTHON=...``). The run stops at the first failing suite and
exits 1, as the former one-command-per-line Make recipe did.

None of these suites needs a database or Docker. ``--list`` prints the commands
without running them.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    # Before/after checks for scripts/normalize_output.sh (also `make test-normalize`).
    ("bash", "scripts/test_normalize_output.sh"),
)


def commands(python: str = sys.executable) -> list[list[str]]:
    """Every suite as an argv, with ``python`` replaced by ``python``."""
    return [[python if arg == "python" else arg for arg in suite] for suite in SUITES]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the commands, run nothing")
    args = parser.parse_args(argv)
    for command in commands():
        print(shlex.join(command), flush=True)
        if args.list:
            continue
        code = subprocess.run(command, cwd=ROOT).returncode
        if code != 0:
            print(f"make test: FAILED (exit {code}): {shlex.join(command)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
