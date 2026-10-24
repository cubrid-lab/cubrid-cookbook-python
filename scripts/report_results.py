#!/usr/bin/env python3
"""report_results.py - Turn JUnit XML into one versioned ``summary.json`` (#461).

``make test`` (``scripts/run_offline_tests.py``) writes one JUnit file per suite under
``test-results/test/junit/`` and calls this module to aggregate them into
``test-results/test/summary.json`` and a one-line console summary generated from the
same data. The functions are reusable by the live-verification side (a follow-up).

Status of a suite, and of the whole run:

- ``FAIL``: a test failed or errored, or the suite exited non-zero (including a missing
  JUnit file after a failure). A run with any failed suite is ``FAIL``.
- ``INCOMPLETE``: nothing proves the suite ran: no JUnit file, nothing collected, or no
  test passed (all skipped or xfailed). A run is ``INCOMPLETE`` when no suite failed but
  one is incomplete or suites were not run (an interrupted run). Never ``PASS``.
- ``PASS``: every suite had at least one passing test, none failed, all exited 0.

JUnit XML cannot tell an unexpected pass of a non-strict xfail from an ordinary pass,
so ``xpassed`` is always 0 (pytest reports a strict xpass, and unittest an unexpected
success, as a failure).

Coverage is not measured by the offline suites, so ``summary.json`` records
``"coverage": {"measured": false}`` and no ``coverage.xml`` is written. This module
adds no coverage gate.

The JUnit files are parsed with the standard library, like ``scripts/live_gate.py``
already does for its own pytest JUnit output. They are produced by this repository's own
test processes in the same run (never downloaded input), and this repository runs no
XML-aware security linter (``ruff`` selects only E4, E7, E9 and F).
"""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
COUNTS = ("selected", "passed", "failed", "errors", "skipped", "xfailed", "xpassed")

# When a test fails and its teardown also errors, pytest writes two <testcase>
# records for it; count each test once, with its worst outcome.
_SEVERITY = {"passed": 0, "xfailed": 1, "skipped": 2, "failed": 3, "errors": 4}


def _outcome(case: ET.Element) -> str:
    if case.find("error") is not None:
        return "errors"
    if case.find("failure") is not None:
        return "failed"
    if (skipped := case.find("skipped")) is not None:
        return "xfailed" if skipped.get("type") == "pytest.xfail" else "skipped"
    return "passed"


def parse_junit(path: Path) -> dict[str, int] | None:
    """Count the tests of a JUnit file; None if it is missing or unreadable."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    outcomes: dict[tuple[str, str], str] = {}
    for case in root.iter("testcase"):
        key = (case.get("classname", ""), case.get("name", ""))
        outcome = _outcome(case)
        if key not in outcomes or _SEVERITY[outcome] > _SEVERITY[outcomes[key]]:
            outcomes[key] = outcome
    counts = dict.fromkeys(COUNTS, 0)
    counts["selected"] = len(outcomes)
    for outcome in outcomes.values():
        counts[outcome] += 1
    return counts


def decide(counts: dict[str, int] | None, exit_code: int) -> str:
    """PASS, FAIL or INCOMPLETE for one suite (see the module docstring)."""
    if counts is None:
        return "FAIL" if exit_code else "INCOMPLETE"
    if counts["failed"] or counts["errors"]:
        return "FAIL"
    if counts["passed"] == 0:
        return "INCOMPLETE"
    return "FAIL" if exit_code else "PASS"


def suite_entry(
    name: str,
    command: Sequence[str],
    exit_code: int,
    junit: Path | None,
    results_dir: Path,
) -> dict[str, Any]:
    """One ``suites`` entry. ``junit`` None means the suite writes no JUnit file (a
    shell script): it counts as one check that passed or failed with its exit status."""
    if junit is None:
        counts: dict[str, int] | None = dict.fromkeys(COUNTS, 0)
        counts["selected"] = 1
        counts["failed" if exit_code else "passed"] = 1
        junit_path = None
    else:
        counts = parse_junit(junit)
        junit_path = junit.relative_to(results_dir).as_posix()
    return {
        "name": name,
        "command": list(command),
        "status": decide(counts, exit_code),
        "exit_code": exit_code,
        "junit": junit_path,
        "counts": counts if counts is not None else dict.fromkeys(COUNTS, 0),
    }


def build_summary(
    lane: str, suites: Sequence[dict[str, Any]], not_run: Sequence[str] = ()
) -> dict[str, Any]:
    """Aggregate suite entries; each test is counted once in exactly one outcome."""
    totals = dict.fromkeys(COUNTS, 0)
    for suite in suites:
        for name in COUNTS:
            totals[name] += suite["counts"][name]
    statuses = {suite["status"] for suite in suites}
    if "FAIL" in statuses:
        status = "FAIL"
    elif "INCOMPLETE" in statuses or not_run or not suites:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "status": status,
        "counts": totals,
        "suites": list(suites),
        "not_run": list(not_run),
        "coverage": {"measured": False},
    }


def console_line(summary: dict[str, Any], summary_path: Path | str | None = None) -> str:
    """The one-line console summary, built only from ``summary`` so they always agree."""
    suites = summary["suites"]
    bad = sum(1 for suite in suites if suite["status"] != "PASS")
    parts = [f"suites={len(suites)}", f"suites_not_passing={bad}"]
    parts += [f"{name}={summary['counts'][name]}" for name in COUNTS]
    if summary["not_run"]:
        parts.append(f"not_run={len(summary['not_run'])}")
    parts.append(
        "coverage=measured" if summary["coverage"]["measured"] else "coverage=not-measured"
    )
    line = f"{summary['lane']}: {summary['status']} " + " ".join(parts)
    return f"{line} -> {summary_path}" if summary_path is not None else line


def write_summary(results_dir: Path, summary: dict[str, Any]) -> Path:
    path = results_dir / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path


def reset_results_dir(results_dir: Path, root: Path) -> None:
    """Empty and recreate ``results_dir`` so stale files never pass for this run's.

    Refuses an empty path, ``.``, ``..``, the filesystem root, the repository root or any directory
    that contains it, and the user's home.
    """
    if results_dir.name in ("", ".", ".."):
        raise ValueError(f"refusing to reset {str(results_dir)!r}")
    resolved = results_dir.resolve()
    home = Path.home().resolve()
    if resolved == Path(resolved.anchor) or resolved == home or home.is_relative_to(resolved):
        raise ValueError(f"refusing to reset {resolved}")
    if resolved == root.resolve() or root.resolve().is_relative_to(resolved):
        raise ValueError(f"refusing to reset {resolved}: it is or contains the repository")
    shutil.rmtree(resolved, ignore_errors=True)
    resolved.mkdir(parents=True)
