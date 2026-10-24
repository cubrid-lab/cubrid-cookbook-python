#!/usr/bin/env python3
"""Live CUBRID verification runner behind ``make verify`` and the ``make verify-*`` lanes (#416).

It adds no test of its own: it reruns the golden-output comparison
(``make verify-goldens``) and the existing pytest suites, one pytest process per
suite (recipes share module names such as ``app``, ``database`` and
``models``), and writes JUnit XML, logs and a grouped summary per lane into
``.live-evidence/<lane>/``. Lanes, in the order ``all`` runs them:

- goldens: every ``expected/*.expected`` golden, compared by ``make verify-goldens``.
- quickstart: FastAPI quickstart ``/health`` and CRUD (#420).
- performance: Java -> Python migration goldens and the fetch/bulk/pooling
  benchmarks (#423).
- web: Flask recipe suites, FastAPI recipe suites and the root FastAPI
  template's SQLite startup test (``/health``; startup only, not live evidence).
- django-celery: Django/SQLAlchemy bridge and async-worker suites. Celery tasks
  run directly (``.run()`` / eager ``.apply()``) without Redis or a worker.
- ai-agent: AI agent state, MCP and RAG scripts, run twice (#422).
- dashboard: Streamlit dashboard AppTest suite on an isolated database
  (``CUBRID_DASHBOARD_TEST_URL``), because the suite drops and recreates its
  own FK-linked tables.

Databases: the goldens, quickstart and performance lanes use the database the
examples hard-code (``localhost:33000/testdb``, started by ``make docker-up``);
web, django-celery and ai-agent use ``CUBRID_TEST_URL``; dashboard uses
``CUBRID_DASHBOARD_TEST_URL``. Both URLs must name dedicated, empty databases,
distinct from each other and from the examples database.

With ``CUBRID_LIVE_GATE=1`` (or ``--gate``) a lane is fail-closed: a missing,
non-``cubrid+pycubrid`` or unreachable URL, URLs that share a database, a
dedicated database that already holds ``cookbook_*`` tables, a suite that
collected no test, skipped any test, printed a database header other than
live CUBRID, or left behind or dropped tables all fail with a nonzero exit.
Without the gate the suites keep their existing behavior (skips, SQLite
fallbacks), and a lane is at best INCOMPLETE, never PASS. ``all`` also checks
every URL, server and example dependency before it runs anything, and writes
``verify-summary.json``/``verify-summary.txt`` with golden and pytest results
reported separately.

    CUBRID_TEST_URL=cubrid+pycubrid://dba@localhost:33005/testdb \\
    CUBRID_DASHBOARD_TEST_URL=cubrid+pycubrid://dba@localhost:33006/testdb \\
        python scripts/live_gate.py --gate all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = ".live-evidence"
GATE_ENV = "CUBRID_LIVE_GATE"
LIVE_URL_ENV = "CUBRID_TEST_URL"
DASHBOARD_URL_ENV = "CUBRID_DASHBOARD_TEST_URL"
# The database every golden example, the quickstart app and the benchmarks
# hard-code: the docker-compose.yml service that `make docker-up` starts.
EXAMPLES_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
REQUIRED_DRIVER = "cubrid+pycubrid"
LIVE_HEADER = re.compile(r"^database: live CUBRID \(", re.MULTILINE)
GATE_ON = {"1", "true", "yes", "on"}
GATE_OFF = {"", "0", "false", "no", "off"}
SUITE_TIMEOUT = 900
EXIT_INCOMPLETE = 3  # `all` without the gate: never a success
PACKAGES = (
    "pycubrid",
    "sqlalchemy",
    "sqlalchemy-cubrid",
    "cubrid-mcp-server",
    "pytest",
    "pytest-asyncio",
    "httpx",
    "uvicorn",
    "pydantic",
    "flask",
    "flask-sqlalchemy",
    "fastapi",
    "django",
    "celery",
    "streamlit",
    "pandas",
    "alembic",
)

# Database modes: "examples" runs on EXAMPLES_URL (shared with the goldens by
# design, so it gets no empty-database check), "live" on CUBRID_TEST_URL,
# "dashboard" on CUBRID_DASHBOARD_TEST_URL, "sqlite" is a by-design SQLite test.
# "keeps_tables" names tables a suite may create and keep (its app's own table).
MANIFEST: dict[str, dict[str, Any]] = {
    "goldens": {
        "title": "Golden output comparisons (make verify-goldens) on the examples database",
        "suites": [{"goldens": ".", "database": "examples"}],
    },
    "quickstart": {
        "title": "FastAPI quickstart /health and CRUD on live CUBRID",
        "suites": [
            {
                "glob": "quickstart/5min-fastapi/tests/test_live.py",
                "database": "examples",
                "keeps_tables": ["cookbook_quickstart_items"],
                "note": "app.py connects to port 33000 and database testdb only, so the "
                "suite runs on the examples database; the app keeps its own table.",
            },
        ],
    },
    "performance": {
        "title": "Java -> Python migration goldens and performance benchmarks on live CUBRID",
        "suites": [
            {
                "glob": "performance/tests/test_benchmarks.py",
                "database": "examples",
                "note": "The scripts hard-code localhost:33000/testdb; timings are parsed, "
                "never compared.",
            },
        ],
    },
    "web": {
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
                "not quickstart health coverage (quickstart lane).",
            },
        ],
    },
    "django-celery": {
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
    "ai-agent": {
        "title": "AI agent state, MCP tools and RAG on live CUBRID",
        "suites": [
            {
                "glob": "templates/ai-agent/tests/test_live.py",
                "database": "live",
                "note": "Each script runs twice for repeatability; the suite drops only "
                "its scripts' own tables before and after each case.",
            },
        ],
    },
    "dashboard": {
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
# `all` (make verify): goldens and the examples-database suites first, then the
# dedicated databases. Lanes run one at a time, so fixed-table suites never overlap.
FULL_ORDER = (
    "goldens",
    "quickstart",
    "performance",
    "web",
    "django-celery",
    "ai-agent",
    "dashboard",
)


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
    """--gate or a recognised on value enables the gate; an unrecognised value is an error."""
    value = environ.get(GATE_ENV, "").strip().lower()
    if value in GATE_ON:
        return True
    if value in GATE_OFF:
        return flag
    raise ValueError(
        f"{GATE_ENV}={value!r} is not one of {sorted(GATE_ON)} (on) or {sorted(GATE_OFF)} (off)"
    )


def expand_suites(lane: str, root: Path = ROOT) -> list[dict[str, Any]]:
    """Expand a lane's manifest globs into sorted suite paths (relative; directories or files)."""
    suites = []
    for entry in MANIFEST[lane]["suites"]:
        if "goldens" in entry:
            suites.append({**entry, "path": entry["goldens"]})
            continue
        matches = sorted(p for p in root.glob(entry["glob"]) if p.is_dir() or p.is_file())
        if not matches:
            raise SystemExit(f"{lane}: manifest glob {entry['glob']!r} matched no suite")
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
        return [f"{name} is not set; the live gate needs a live CUBRID database"]
    from sqlalchemy.engine import make_url

    try:
        parsed = make_url(url)
    except Exception as error:
        return [f"{name} is not a valid SQLAlchemy URL: {error}"]
    if parsed.drivername != REQUIRED_DRIVER:
        return [
            f"{name} uses {parsed.drivername!r}; the live gate requires a "
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
    """Static gate checks for the URLs a lane needs (no connection is opened)."""
    if not gate:
        return []
    reasons: list[str] = []
    examples = database_identity(EXAMPLES_URL)
    for mode, name, url in (
        ("live", LIVE_URL_ENV, live_url),
        ("dashboard", DASHBOARD_URL_ENV, dashboard_url),
    ):
        if mode not in needs:
            continue
        problems = check_url(name, url)
        reasons += problems
        if not problems and database_identity(url or "") == examples:
            reasons.append(
                f"{name} points at the examples database ({shown_url(EXAMPLES_URL)}) that "
                "make docker-up starts and the goldens share; use a dedicated, empty database"
            )
    if "dashboard" in needs and not check_url(DASHBOARD_URL_ENV, dashboard_url):
        if live_url and not check_url(LIVE_URL_ENV, live_url):
            if database_identity(live_url) == database_identity(dashboard_url or ""):
                reasons.append(
                    f"{DASHBOARD_URL_ENV} points at the same database as {LIVE_URL_ENV}; "
                    "the dashboard suite needs an isolated database"
                )
    return reasons


def baseline_reasons(env_name: str, tables: set[str]) -> list[str]:
    """Refuse a database that already holds cookbook tables: suites may drop them."""
    existing = sorted(name for name in tables if name.startswith("cookbook_"))
    if not existing:
        return []
    return [
        f"{env_name} already contains cookbook_* tables {existing}; the suites drop and "
        "recreate their own tables, so use a dedicated, empty database"
    ]


def table_change_reasons(
    before: set[str], after: set[str], keeps: tuple[str, ...] | list[str] = ()
) -> list[str]:
    """Tables a suite left behind or dropped, compared with its own pre-run snapshot."""
    reasons = []
    if created := sorted(after - before - set(keeps)):
        reasons.append(f"left new tables behind: {created}")
    if dropped := sorted(before - after):
        reasons.append(f"dropped pre-existing tables: {dropped}")
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
        reasons.append(f"{result.skipped} skipped; the live gate accepts no skipped test")
    if gate and live_header and not LIVE_HEADER.search(output):
        reasons.append("pytest did not report the 'database: live CUBRID (...)' header")
    if reasons:
        result.status = "failed"
    elif result.skipped:
        result.status = "incomplete"
        reasons.append(f"{result.skipped} skipped (not gate evidence)")
    else:
        result.status = "passed"


def lane_status(results: list[SuiteResult], reasons: list[str], gate: bool) -> str:
    """Only a gated run can PASS; an ungated one may have used skips or SQLite fallbacks."""
    if reasons or not results or any(r.status == "failed" for r in results):
        return "FAIL"
    if not gate or any(r.status != "passed" for r in results):
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

    dirty = run("status", "--porcelain", "--untracked-files=no")
    return {"sha": run("rev-parse", "HEAD") or None, "dirty": bool(dirty)}


VERSIONS_CODE = """
import json, platform
from importlib import metadata
packages = {}
for name in %r:
    try:
        packages[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        packages[name] = None
print(json.dumps({"version": platform.python_version(), "packages": packages}))
"""


def interpreter_versions(python: str) -> dict[str, Any]:
    """Python and package versions of the interpreter that runs pytest."""
    try:
        completed = subprocess.run(
            [python, "-c", VERSIONS_CODE % (PACKAGES,)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        return {"version": None, "packages": {}, "error": f"{type(error).__name__}: {error}"}


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


def suite_env(
    database: str, live_url: str | None, dashboard_url: str | None, gate: bool
) -> dict[str, str]:
    env = dict(os.environ)
    env.pop(LIVE_URL_ENV, None)
    env.pop("VERIFY_SCOPE", None)  # only run_goldens may mark a run as the full verification
    # The suites read the gate as exactly "1"; normalise any accepted spelling.
    env[GATE_ENV] = "1" if gate else "0"
    if gate:
        # Ambient pytest options or plugins could deselect or skip tests unseen.
        env.pop("PYTEST_ADDOPTS", None)
        env.pop("PYTEST_PLUGINS", None)
    url = {"live": live_url, "dashboard": dashboard_url, "examples": EXAMPLES_URL}.get(database)
    if url:
        env[LIVE_URL_ENV] = url
    return env


GOLDEN_PASS = "PASS"
GOLDEN_SKIP = "SKIP"


def run_goldens(
    suite: dict[str, Any], out_dir: Path, python: str, env: dict[str, str], partial: bool = True
) -> tuple[SuiteResult, str]:
    """Run `make verify-goldens` and read its per-golden result lines.

    The recipe appends one ``STATUS<TAB>target`` line per golden to the file named
    by the ``VERIFY_RESULTS`` environment variable.
    """
    results_file = out_dir / "results.tsv"
    env = {**env, "VERIFY_RESULTS": str(results_file)}
    if not partial:
        env["VERIFY_SCOPE"] = "full"  # the goldens part of `make verify`: no PARTIAL line
    command = [
        shutil.which("make") or "make",
        "--no-print-directory",
        "-f",
        str(ROOT / "Makefile"),
        "verify-goldens",
        f"VERIFY_PATHS={suite['path']}",
        f"PYTHON={python}",
    ]
    result = SuiteResult("golden outputs", suite["database"], command, note=suite.get("note", ""))
    started = time.monotonic()
    lines: list[str] = []
    try:
        # Stream: a full golden run takes minutes, and its PASS/MISMATCH lines are the log.
        with subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                lines.append(line)
        result.returncode = process.returncode
    except OSError as error:
        result.reasons.append(f"could not run make verify-goldens: {error}")
    result.duration = round(time.monotonic() - started, 2)
    output = "".join(lines)
    (out_dir / "goldens.log").write_text(output, encoding="utf-8")
    rows = []
    if results_file.is_file():
        for row in results_file.read_text(encoding="utf-8").splitlines():
            status, _, target = row.partition("\t")
            rows.append({"id": target, "outcome": status})
    result.cases = rows
    result.tests = len(rows)
    result.passed = sum(row["outcome"] == GOLDEN_PASS for row in rows)
    result.skipped = sum(row["outcome"] == GOLDEN_SKIP for row in rows)
    result.failed = result.tests - result.passed - result.skipped
    if result.returncode not in (0, None):
        result.reasons.append(f"make verify-goldens exited {result.returncode}")
    if result.tests == 0:
        result.reasons.append("no golden was compared")
    if result.failed or result.skipped:
        result.reasons.append(f"{result.failed} failed, {result.skipped} skipped goldens")
    result.status = "failed" if result.reasons else "passed"
    return result, output


def probe_servers(
    needs: set[str], live_url: str | None, dashboard_url: str | None, gate: bool
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Probe each database a lane needs: version, reachability and (dedicated ones) emptiness."""
    servers: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for mode, env_name, url in (
        ("examples", "make up", EXAMPLES_URL),
        ("live", LIVE_URL_ENV, live_url),
        ("dashboard", DASHBOARD_URL_ENV, dashboard_url),
    ):
        if mode not in needs or not url or (mode != "examples" and check_url(env_name, url)):
            continue
        version, tables, error = probe(url)
        servers[mode] = {"env": env_name, "url": shown_url(url), "version": version, "error": error}
        if gate and error and mode == "examples":
            reasons.append(
                f"the examples database ({shown_url(url)}) is unreachable: {error}; run make docker-up"
            )
        elif gate and error:
            reasons.append(f"{env_name} is unreachable: {error}")
        elif gate and mode != "examples":
            # The examples database keeps the goldens' fixed tables by design.
            reasons += baseline_reasons(env_name, tables or set())
    return servers, reasons


def run_lane(
    lane: str, evidence_dir: Path, gate: bool, python: str, timeout: int, partial: bool = True
) -> dict[str, Any]:
    """Run one lane. ``partial`` is False only for the lanes of the full ``make verify``."""
    live_url = os.environ.get(LIVE_URL_ENV) or None
    dashboard_url = os.environ.get(DASHBOARD_URL_ENV) or None
    suites = expand_suites(lane)
    needs = {suite["database"] for suite in suites}
    out_dir = evidence_dir / lane
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    reasons = preflight(needs, live_url, dashboard_url, gate)
    servers, probe_reasons = probe_servers(needs, live_url, dashboard_url, gate)
    reasons += probe_reasons

    results: list[SuiteResult] = []
    if not reasons:
        for suite in suites:
            if "goldens" in suite:
                print(f"[{lane}] make verify-goldens ({suite['database']})", flush=True)
                env = suite_env("sqlite", live_url, dashboard_url, gate)
                result, _ = run_goldens(suite, out_dir, python, env, partial)
                print(f"[{lane}]   -> {result.status}: {_counts(result)}", flush=True)
                results.append(result)
                continue
            print(f"[{lane}] pytest {suite['path']} ({suite['database']})", flush=True)
            env = suite_env(suite["database"], live_url, dashboard_url, gate)
            check_tables = gate and suite["database"] in servers
            if check_tables:
                _, before, before_error = probe(env[LIVE_URL_ENV])
            result, output = run_suite(suite, out_dir, python, env, timeout)
            judge(result, gate, output, suite.get("live_header", False))
            if check_tables:
                _, after, error = probe(env[LIVE_URL_ENV])
                changes = (
                    [f"table snapshot failed: {before_error or error}"]
                    if before_error or error
                    else table_change_reasons(
                        before or set(), after or set(), suite.get("keeps_tables", ())
                    )
                )
                if changes:
                    result.status = "failed"
                    result.reasons += changes
            print(f"[{lane}]   -> {result.status}: {_counts(result)}", flush=True)
            results.append(result)

    versions = interpreter_versions(python)
    summary = {
        "lane": lane,
        "title": MANIFEST[lane]["title"],
        "status": lane_status(results, reasons, gate),
        "gate": gate,
        "partial": partial,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "python": {
            "version": versions["version"],
            "executable": python,
            **({"error": versions["error"]} if "error" in versions else {}),
        },
        "packages": versions["packages"],
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


def partial_line(lanes: list[str]) -> str:
    """The console/summary line of a run that is not the full ``make verify``."""
    return (
        f"PARTIAL: checked only the {', '.join(lanes)} lane{'s' if len(lanes) > 1 else ''}; "
        "this is not the full verification (only a passing `make verify` is)."
    )


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"== {summary['lane']}: {summary['title']} -> {summary['status']}",
        f"gate: {'on' if summary['gate'] else 'off'}   generated: {summary['generated_at']}",
        f"git: {summary['git']['sha']}{' (dirty)' if summary['git']['dirty'] else ''}",
        f"python: {summary['python']['version']}   "
        + ", ".join(f"{k} {v}" for k, v in summary["packages"].items() if v),
    ]
    if summary["partial"]:
        lines.insert(1, partial_line([summary["lane"]]))
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


def missing_dependencies(python: str) -> list[str]:
    """Run the example dependency check (every example requirements.txt) under `python`."""
    try:
        completed = subprocess.run(
            [python, str(ROOT / "scripts" / "example_requirements.py"), "--check", "--all"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return [f"dependency check failed: {type(error).__name__}: {error}"]
    if completed.returncode == 0:
        return []
    detail = (completed.stderr or completed.stdout).strip()
    return [f"missing example dependencies (run make deps):\n{detail}"]


def run_all(evidence_dir: Path, gate: bool, python: str, timeout: int) -> dict[str, Any]:
    """Full verification: check every database and dependency first, then run every lane."""
    for name in ("verify-summary.json", "verify-summary.txt"):
        # A stale summary must never stand in for this run's result.
        (evidence_dir / name).unlink(missing_ok=True)
    live_url = os.environ.get(LIVE_URL_ENV) or None
    dashboard_url = os.environ.get(DASHBOARD_URL_ENV) or None
    needs = {suite["database"] for lane in FULL_ORDER for suite in expand_suites(lane)}
    reasons = preflight(needs, live_url, dashboard_url, gate)
    servers, probe_reasons = probe_servers(needs, live_url, dashboard_url, gate)
    reasons += probe_reasons + missing_dependencies(python)

    lanes: dict[str, dict[str, Any]] = {}
    if not reasons:
        for lane in FULL_ORDER:
            lanes[lane] = run_lane(lane, evidence_dir, gate, python, timeout, partial=False)

    def totals(names: list[str], live: bool) -> dict[str, int]:
        # By-design SQLite suites (startup-only) are counted apart from live evidence.
        suites = [
            suite
            for name in names
            if name in lanes
            for suite in lanes[name]["suites"]
            if (suite["database"] != "sqlite") == live
        ]
        return {
            key: sum(suite[key] for suite in suites)
            for key in ("tests", "passed", "failed", "errors", "skipped")
        }

    def section(names: list[str]) -> dict[str, Any]:
        statuses = [lanes[name]["status"] for name in names if name in lanes]
        return {
            "status": lane_status_of(statuses, len(names)),
            "totals": totals(names, live=True),
            "non_live_totals": totals(names, live=False),
            "lanes": {
                name: {
                    "status": lanes[name]["status"],
                    "totals": lanes[name]["totals"],
                    "summary": shown_path(evidence_dir / name / "summary.json"),
                }
                for name in names
                if name in lanes
            },
        }

    goldens = section(["goldens"])
    failed_goldens = [
        case
        for suite in lanes.get("goldens", {}).get("suites", [])
        for case in suite["cases"]
        if case["outcome"] != GOLDEN_PASS
    ]
    goldens["failures"] = failed_goldens
    pytest_lanes = section([lane for lane in FULL_ORDER if lane != "goldens"])
    versions = interpreter_versions(python)
    summary = {
        "scope": "full",
        "partial": False,
        "status": "FAIL"
        if reasons
        else lane_status_of([goldens["status"], pytest_lanes["status"]], 2),
        "gate": gate,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "python": {
            "version": versions["version"],
            "executable": python,
            **({"error": versions["error"]} if "error" in versions else {}),
        },
        "packages": versions["packages"],
        "servers": servers,
        "preflight_failures": reasons,
        "goldens": goldens,
        "pytest": pytest_lanes,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "verify-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    text = render_verify_text(summary)
    (evidence_dir / "verify-summary.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    return summary


def shown_path(path: Path) -> str:
    """A repository-relative path when possible, so summaries do not leak home directories."""
    return (path.relative_to(ROOT) if path.is_relative_to(ROOT) else path).as_posix()


def lane_status_of(statuses: list[str], expected: int) -> str:
    """Combine lane statuses: any FAIL, or a lane that never ran, fails the whole."""
    if len(statuses) < expected or "FAIL" in statuses:
        return "FAIL"
    return "PASS" if all(status == "PASS" for status in statuses) else "INCOMPLETE"


def render_verify_text(summary: dict[str, Any]) -> str:
    lines = [
        f"== make verify (full): {summary['status']}",
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
    for title, key in (("golden outputs", "goldens"), ("pytest suites", "pytest")):
        part = summary[key]
        totals = part["totals"]
        lines.append(
            f"{title}: {part['status']} ({totals['tests']} run, {totals['passed']} passed, "
            f"{totals['failed']} failed, {totals['errors']} errors, {totals['skipped']} skipped)"
        )
        other = part["non_live_totals"]
        if other["tests"]:
            lines.append(
                f"  plus {other['tests']} non-live (by-design SQLite, startup-only) tests: "
                f"{other['passed']} passed, {other['failed']} failed, {other['errors']} errors"
            )
        for name, lane in part["lanes"].items():
            lines.append(f"  [{lane['status']}] {name} -> {lane['summary']}")
    for case in summary["goldens"].get("failures", []):
        lines.append(f"  golden {case['outcome']}: {case['id']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "lanes",
        nargs="+",
        choices=[*sorted(MANIFEST), "all"],
        help="lanes to run in order; 'all' is the full make verify run",
    )
    parser.add_argument("--gate", action="store_true", help=f"fail closed (same as {GATE_ENV}=1)")
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--python", default=sys.executable, help="interpreter that runs pytest")
    parser.add_argument("--timeout", type=int, default=SUITE_TIMEOUT, help="seconds per suite")
    args = parser.parse_args(argv)

    try:
        gate = gate_enabled(args.gate)
    except ValueError as error:
        parser.error(str(error))
    try:
        import sqlalchemy  # noqa: F401  (URL checks and database probes)
    except ImportError:
        print("live_gate.py needs SQLAlchemy and the CUBRID drivers: run `make deps` first.")
        return 1
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    if "all" in args.lanes:
        if len(args.lanes) > 1:
            parser.error("'all' runs every lane; do not combine it with other lanes")
        summary = run_all(evidence_dir, gate, args.python, args.timeout)
        # Full verification succeeds only on PASS; INCOMPLETE (ungated) gets its own code.
        return {"PASS": 0, "FAIL": 1}.get(summary["status"], EXIT_INCOMPLETE)
    statuses = {}
    for lane in dict.fromkeys(args.lanes):
        statuses[lane] = run_lane(lane, evidence_dir, gate, args.python, args.timeout)["status"]
    print(partial_line(list(statuses)))
    print("live gate: " + ", ".join(f"{lane} {status}" for lane, status in statuses.items()))
    return 0 if all(status != "FAIL" for status in statuses.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
