#!/usr/bin/env python3
"""Rerunnable evidence lane for feature specs 08-10 (#421).

Runs the existing template pytest suites -- it adds no test of its own -- one
pytest process per suite (recipes share module names such as ``app``,
``database`` and ``models``), and writes JUnit XML, logs and a grouped summary
per spec into ``.spec-evidence/<spec>/``:

- spec-08: Flask recipe suites, FastAPI recipe suites and the root FastAPI
  template's SQLite startup test (``/health``; startup only, not live evidence).
- spec-09: Django/SQLAlchemy bridge and async-worker suites. Celery tasks run
  directly (``.run()`` / eager ``.apply()``) without Redis or a worker.
- spec-10: Streamlit dashboard AppTest suite on an isolated database
  (``CUBRID_DASHBOARD_TEST_URL``), because the suite drops and recreates its
  own FK-linked tables.

With ``CUBRID_SPEC_GATE=1`` (or ``--gate``) the lane is fail-closed: a missing,
non-``cubrid+pycubrid`` or unreachable URL, a dashboard URL equal to the main
one, a suite that collected no test, skipped any test, did not report live
CUBRID, or left new tables behind all fail with a nonzero exit. Without the
gate the suites keep their existing behavior (skips, SQLite fallbacks), and
the summary marks such a spec INCOMPLETE rather than PASS.

    CUBRID_SPEC_GATE=1 CUBRID_TEST_URL=cubrid+pycubrid://dba@localhost:33000/testdb \\
        python scripts/spec_gate.py spec-08 spec-09
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = ".spec-evidence"
GATE_ENV = "CUBRID_SPEC_GATE"
LIVE_URL_ENV = "CUBRID_TEST_URL"
DASHBOARD_URL_ENV = "CUBRID_DASHBOARD_TEST_URL"
REQUIRED_DRIVER = "cubrid+pycubrid"
LIVE_HEADER = "database: live CUBRID"
SUITE_TIMEOUT = 900
PACKAGES = (
    "pycubrid",
    "sqlalchemy",
    "sqlalchemy-cubrid",
    "pytest",
    "flask",
    "flask-sqlalchemy",
    "fastapi",
    "django",
    "celery",
    "streamlit",
)

# Database modes: "live" runs on CUBRID_TEST_URL, "dashboard" on
# CUBRID_DASHBOARD_TEST_URL, "sqlite" is a by-design SQLite test (no URL).
MANIFEST: dict[str, dict[str, Any]] = {
    "spec-08": {
        "title": "Flask and FastAPI templates on live CUBRID",
        "suites": [
            {"glob": "templates/flask/*/tests", "database": "live", "live_header": True},
            {
                "glob": "templates/api-service-fastapi/recipes/*/tests",
                "database": "live",
                "live_header": True,
            },
            {
                "glob": "templates/api-service-fastapi/tests",
                "database": "sqlite",
                "note": "Root FastAPI template startup and /health on a throwaway SQLite "
                "file by design; startup evidence only, not live CUBRID evidence and "
                "not quickstart health coverage (spec 03).",
            },
        ],
    },
    "spec-09": {
        "title": "Django bridge and Celery worker tasks on live CUBRID",
        "suites": [
            {
                "glob": "templates/django/tests",
                "database": "live",
                "note": "Django HTTP views save/read through the SQLAlchemy bridge, then "
                "update/delete; the fixture refuses a preexisting cookbook_django_items.",
            },
            {
                "glob": "templates/async-worker/tests",
                "database": "live",
                "note": "Celery tasks run directly (.run() / eager .apply()) without a "
                "Redis broker or a worker process: this is task persistence evidence, "
                "not worker-dispatch end-to-end evidence.",
            },
        ],
    },
    "spec-10": {
        "title": "Streamlit dashboard on an isolated live CUBRID database",
        "suites": [
            {
                "glob": "templates/dashboard/tests",
                "database": "dashboard",
                "live_header": True,
                "note": "Runs on CUBRID_DASHBOARD_TEST_URL: the suite drops and recreates "
                "its FK-linked cookbook_dashboard_products/cookbook_dashboard_sales.",
            },
        ],
    },
}


@dataclass
class SuiteResult:
    path: str
    database: str
    command: list[str]
    returncode: int | None = None
    tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    status: str = "not-run"
    reasons: list[str] = field(default_factory=list)
    cases: list[dict[str, str]] = field(default_factory=list)
    note: str = ""


def gate_enabled(flag: bool, environ: dict[str, str] | os._Environ[str] = os.environ) -> bool:
    return flag or environ.get(GATE_ENV, "").strip() == "1"


def expand_suites(spec: str, root: Path = ROOT) -> list[dict[str, Any]]:
    """Expand a spec's manifest globs into sorted suite directories (relative paths)."""
    suites = []
    for entry in MANIFEST[spec]["suites"]:
        matches = sorted(p for p in root.glob(entry["glob"]) if p.is_dir())
        if not matches:
            raise SystemExit(f"{spec}: manifest glob {entry['glob']!r} matched no suite")
        for match in matches:
            suites.append({**entry, "path": match.relative_to(root).as_posix()})
    return suites


def shown_url(url: str) -> str:
    from sqlalchemy.engine import make_url

    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable URL>"


def check_url(name: str, url: str | None) -> list[str]:
    """Reasons a URL cannot serve as gate evidence (empty when it is acceptable)."""
    if not url:
        return [f"{name} is not set; the spec gate needs a live CUBRID database"]
    from sqlalchemy.engine import make_url

    try:
        parsed = make_url(url)
    except Exception as error:
        return [f"{name} is not a valid SQLAlchemy URL: {error}"]
    if parsed.drivername != REQUIRED_DRIVER:
        return [
            f"{name} uses {parsed.drivername!r}; the spec gate requires a "
            f"{REQUIRED_DRIVER}:// URL (no SQLite or other fallback)"
        ]
    return []


def database_identity(url: str) -> tuple[str, int, str]:
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    host = (parsed.host or "localhost").lower()
    if host in {"127.0.0.1", "::1"}:
        host = "localhost"
    return host, parsed.port or 33000, (parsed.database or "").lower()


def preflight(
    needs: set[str], live_url: str | None, dashboard_url: str | None, gate: bool
) -> list[str]:
    """Static gate checks for the URLs a spec needs (no connection is opened)."""
    if not gate:
        return []
    reasons: list[str] = []
    if "live" in needs:
        reasons += check_url(LIVE_URL_ENV, live_url)
    if "dashboard" in needs:
        problems = check_url(DASHBOARD_URL_ENV, dashboard_url)
        reasons += problems
        if not problems and live_url and not check_url(LIVE_URL_ENV, live_url):
            if database_identity(live_url) == database_identity(dashboard_url or ""):
                reasons.append(
                    f"{DASHBOARD_URL_ENV} points at the same database as {LIVE_URL_ENV}; "
                    "the dashboard suite needs an isolated database"
                )
    return reasons


def probe(url: str) -> tuple[str | None, set[str] | None, str | None]:
    """Return (server version, table names, error) for a live CUBRID URL."""
    try:
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.pool import NullPool

        engine = create_engine(
            url, poolclass=NullPool, connect_args={"connect_timeout": 10, "read_timeout": 30}
        )
        try:
            with engine.connect() as connection:
                version = str(connection.execute(text("SELECT VERSION()")).scalar_one())
            tables = {name.casefold() for name in inspect(engine).get_table_names()}
        finally:
            engine.dispose()
        return version, tables, None
    except Exception as error:
        return None, None, f"{type(error).__name__}: {error}".strip()


def parse_junit(path: Path) -> dict[str, Any]:
    """Sum pytest JUnit counts; raises ValueError when the file is missing or malformed."""
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        raise ValueError(f"no readable JUnit XML at {path}: {error}") from error
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    cases: list[dict[str, str]] = []
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, 0))
        for case in suite.iter("testcase"):
            outcome = "passed"
            for tag in ("failure", "error", "skipped"):
                if case.find(tag) is not None:
                    outcome = {"failure": "failed"}.get(tag, tag)
                    break
            cases.append(
                {"id": f"{case.get('classname', '')}::{case.get('name', '')}", "outcome": outcome}
            )
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    return {**counts, "cases": cases}


def judge(result: SuiteResult, gate: bool, output: str, live_header: bool) -> None:
    """Set result.status/reasons. Statuses: passed, incomplete (skips, no gate), failed."""
    reasons = result.reasons
    if result.returncode != 0:
        reasons.append(f"pytest exited {result.returncode}")
    if result.tests == 0:
        reasons.append("no test was collected or run")
    if result.failed or result.errors:
        reasons.append(f"{result.failed} failed, {result.errors} errors")
    if result.skipped and gate:
        reasons.append(f"{result.skipped} skipped; the spec gate accepts no skipped test")
    if gate and live_header and LIVE_HEADER not in output:
        reasons.append(f"pytest did not report '{LIVE_HEADER}'")
    if reasons:
        result.status = "failed"
    elif result.skipped:
        result.status = "incomplete"
        reasons.append(f"{result.skipped} skipped (not gate evidence)")
    else:
        result.status = "passed"


def spec_status(results: list[SuiteResult], reasons: list[str]) -> str:
    if reasons or not results or any(r.status == "failed" for r in results):
        return "FAIL"
    if any(r.status != "passed" for r in results):
        return "INCOMPLETE"
    return "PASS"


def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {"sha": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def run_suite(
    suite: dict[str, Any], out_dir: Path, python: str, env: dict[str, str], timeout: int
) -> tuple[SuiteResult, str]:
    slug = suite["path"].replace("/", "__")
    junit = out_dir / f"{slug}.xml"
    command = [
        python,
        "-m",
        "pytest",
        suite["path"],
        "-v",
        "-rs",
        "--tb=short",
        "-p",
        "no:cacheprovider",
        f"--junitxml={junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit}",
    ]
    result = SuiteResult(suite["path"], suite["database"], command, note=suite.get("note", ""))
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout
        )
        result.returncode = completed.returncode
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as error:
        result.reasons.append(f"timed out after {timeout}s")
        output = "\n".join(
            part.decode() if isinstance(part, bytes) else (part or "")
            for part in (error.stdout, error.stderr)
        )
    result.duration = round(time.monotonic() - started, 2)
    (out_dir / f"{slug}.log").write_text(output, encoding="utf-8")
    try:
        counts = parse_junit(junit)
        result.tests, result.skipped = counts["tests"], counts["skipped"]
        result.failed, result.errors = counts["failures"], counts["errors"]
        result.passed, result.cases = counts["passed"], counts["cases"]
    except ValueError as error:
        result.reasons.append(str(error))
    return result, output


def suite_env(database: str, live_url: str | None, dashboard_url: str | None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop(LIVE_URL_ENV, None)
    url = {"live": live_url, "dashboard": dashboard_url}.get(database)
    if url:
        env[LIVE_URL_ENV] = url
    return env


def run_spec(
    spec: str, evidence_dir: Path, gate: bool, python: str, timeout: int
) -> dict[str, Any]:
    live_url = os.environ.get(LIVE_URL_ENV) or None
    dashboard_url = os.environ.get(DASHBOARD_URL_ENV) or None
    suites = expand_suites(spec)
    needs = {suite["database"] for suite in suites}
    out_dir = evidence_dir / spec
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    reasons = preflight(needs, live_url, dashboard_url, gate)
    servers: dict[str, dict[str, Any]] = {}
    for mode, env_name, url in (
        ("live", LIVE_URL_ENV, live_url),
        ("dashboard", DASHBOARD_URL_ENV, dashboard_url),
    ):
        if mode not in needs or not url or check_url(env_name, url):
            continue
        version, tables, error = probe(url)
        servers[mode] = {"env": env_name, "url": shown_url(url), "version": version, "error": error}
        servers[mode]["_tables"] = tables
        if error and gate:
            reasons.append(f"{env_name} is unreachable: {error}")

    results: list[SuiteResult] = []
    if not reasons:
        for suite in suites:
            print(f"[{spec}] pytest {suite['path']} ({suite['database']})", flush=True)
            env = suite_env(suite["database"], live_url, dashboard_url)
            result, output = run_suite(suite, out_dir, python, env, timeout)
            judge(result, gate, output, suite.get("live_header", False))
            server = servers.get(suite["database"])
            if gate and server and server["_tables"] is not None:
                _, after, error = probe(env[LIVE_URL_ENV])
                leftover = sorted((after or set()) - server["_tables"])
                if error or leftover:
                    result.status = "failed"
                    result.reasons.append(
                        f"post-run table check failed: {error}"
                        if error
                        else f"left new tables behind: {leftover}"
                    )
            print(f"[{spec}]   -> {result.status}: {_counts(result)}", flush=True)
            results.append(result)

    for server in servers.values():
        server.pop("_tables", None)
    summary = {
        "spec": spec,
        "title": MANIFEST[spec]["title"],
        "status": spec_status(results, reasons),
        "gate": gate,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "python": {"version": platform.python_version(), "executable": python},
        "packages": package_versions(),
        "servers": servers,
        "preflight_failures": reasons,
        "totals": {
            key: sum(getattr(r, key) for r in results)
            for key in ("tests", "passed", "failed", "errors", "skipped")
        },
        "suites": [
            {
                "path": r.path,
                "database": r.database,
                "status": r.status,
                "tests": r.tests,
                "passed": r.passed,
                "failed": r.failed,
                "errors": r.errors,
                "skipped": r.skipped,
                "returncode": r.returncode,
                "duration_seconds": r.duration,
                "command": " ".join(r.command),
                "reasons": r.reasons,
                "note": r.note,
                "cases": r.cases,
            }
            for r in results
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    text = render_text(summary)
    (out_dir / "summary.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    return summary


def _counts(result: SuiteResult) -> str:
    return (
        f"{result.tests} selected, {result.passed} passed, {result.failed} failed, "
        f"{result.errors} errors, {result.skipped} skipped"
    )


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"== {summary['spec']}: {summary['title']} -> {summary['status']}",
        f"gate: {'on' if summary['gate'] else 'off'}   generated: {summary['generated_at']}",
        f"git: {summary['git']['sha']}{' (dirty)' if summary['git']['dirty'] else ''}",
        f"python: {summary['python']['version']}   "
        + ", ".join(f"{k} {v}" for k, v in summary["packages"].items() if v),
    ]
    for mode, server in summary["servers"].items():
        lines.append(
            f"{mode} server ({server['env']}={server['url']}): "
            + (server["version"] or f"unreachable: {server['error']}")
        )
    for reason in summary["preflight_failures"]:
        lines.append(f"PREFLIGHT FAIL: {reason}")
    for suite in summary["suites"]:
        lines.append(
            f"  [{suite['status'].upper()}] {suite['path']} ({suite['database']}): "
            f"{suite['tests']} selected, {suite['passed']} passed, {suite['failed']} failed, "
            f"{suite['errors']} errors, {suite['skipped']} skipped"
        )
        lines.append(f"      command: {suite['command']}")
        if suite["note"]:
            lines.append(f"      note: {suite['note']}")
        for reason in suite["reasons"]:
            lines.append(f"      reason: {reason}")
    totals = summary["totals"]
    lines.append(
        f"totals: {totals['tests']} selected, {totals['passed']} passed, {totals['failed']} "
        f"failed, {totals['errors']} errors, {totals['skipped']} skipped"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("specs", nargs="+", choices=sorted(MANIFEST))
    parser.add_argument("--gate", action="store_true", help=f"fail closed (same as {GATE_ENV}=1)")
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--python", default=sys.executable, help="interpreter that runs pytest")
    parser.add_argument("--timeout", type=int, default=SUITE_TIMEOUT, help="seconds per suite")
    args = parser.parse_args(argv)

    gate = gate_enabled(args.gate)
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    statuses = {}
    for spec in dict.fromkeys(args.specs):
        statuses[spec] = run_spec(spec, evidence_dir, gate, args.python, args.timeout)["status"]
    print("spec gate: " + ", ".join(f"{spec} {status}" for spec, status in statuses.items()))
    return 0 if all(status != "FAIL" for status in statuses.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
