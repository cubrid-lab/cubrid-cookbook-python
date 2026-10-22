"""Live evidence (#423): Java -> Python migration goldens and performance benchmarks.

Two groups, reported as separate JUnit classes:

* ``TestMigrationGoldens`` re-runs the five ``migration/java-to-python`` golden cases
  with the same comparison as ``make verify`` (run the script with stderr merged,
  pipe it through ``scripts/normalize_output.sh``, compare with ``expected/*.expected``).
* ``TestPerformanceBenchmarks`` runs the three ``performance/*/benchmark.py`` scripts and
  checks that they finish, print every comparison line with a finite, nonnegative
  time, really run their configured workload, and drop their benchmark tables, also
  when the benchmark raises. Elapsed times are only parsed, never compared with
  each other or with a threshold, and never written to a golden.

The scripts hard-code ``localhost:33000``, database ``testdb``, user ``dba`` (the
repository's ``docker-compose.yml``), so the tests probe that endpoint. Without a
reachable database they skip. With ``CUBRID_LIVE_GATE=1`` (``make verify-performance``, ``make verify``) an
unreachable database or a missing driver fails the run instead.
"""

from __future__ import annotations

import importlib.metadata
import math
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_EXAMPLE = ROOT / "scripts" / "run_example.py"
NORMALIZE = ROOT / "scripts" / "normalize_output.sh"
MIGRATION_DIR = ROOT / "migration" / "java-to-python"
PERFORMANCE_DIR = ROOT / "performance"

GATE = os.environ.get("CUBRID_LIVE_GATE") == "1"
# The endpoint every script under test hard-codes.
DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}

MIGRATION_CASES = sorted(path.stem for path in (MIGRATION_DIR / "expected").glob("*.expected"))
MIGRATION_TIMEOUT = 60  # same per-script limit as `make verify` (VERIFY_TIMEOUT)

# Workloads configured in the benchmark scripts; the printed evidence must match them.
FETCH_ROWS = 10_000
BULK_ROWS = {1: 500, 2: 5_000, 3: 5_000}
POOL_QUERIES = 50
POOL_SIZE = 5

FAILURE_PATTERN = re.compile(r"Traceback|\b\w*(Error|Exception)\b")
NUMBER = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|nan|inf)"

# Runs a benchmark with pycubrid.connect patched so that the first statement starting
# with argv[2] raises. Before raising it records whether the benchmark table argv[3]
# exists, which proves the cleanup in the script's `finally` block had work to do.
FAULT_RUNNER = """
import runpy
import sys

import pycubrid

script, fail_prefix, table = sys.argv[1], sys.argv[2].upper(), sys.argv[3]
real_connect = pycubrid.connect


class FaultyCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, *args, **kwargs):
        if sql.lstrip().upper().startswith(fail_prefix):
            self._cursor.execute(
                "SELECT COUNT(*) FROM db_class WHERE class_name = ?", (table,)
            )
            print(f"perf-fault: {table} present at failure: {self._cursor.fetchone()[0]}")
            raise RuntimeError(f"perf-fault injected failure before {fail_prefix}")
        return self._cursor.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class FaultyConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return FaultyCursor(self._conn.cursor(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self._conn, name)


pycubrid.connect = lambda *args, **kwargs: FaultyConnection(real_connect(*args, **kwargs))
sys.argv = [script]
runpy.run_path(script, run_name="__main__")
"""


def _unavailable(reason: str) -> None:
    if GATE:
        pytest.fail(f"CUBRID_LIVE_GATE=1: {reason}", pytrace=False)
    pytest.skip(reason)


def _version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


class LiveDB:
    """Short-lived connections to the scripts' database for state checks."""

    def __init__(self, pycubrid_module: object) -> None:
        self._pycubrid = pycubrid_module

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        conn = self._pycubrid.connect(**DB_CONFIG)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall() if cursor.description else []
            conn.commit()
            return [tuple(row) for row in rows]
        finally:
            conn.close()

    def table_exists(self, table: str) -> bool:
        rows = self.query("SELECT COUNT(*) FROM db_class WHERE class_name = ?", (table,))
        return rows[0][0] > 0


@pytest.fixture(scope="session")
def live_db(record_testsuite_property, pytestconfig) -> LiveDB:
    try:
        import pycubrid
        import sqlalchemy_cubrid  # noqa: F401  (connection-pooling benchmark dialect)
    except ImportError as exc:
        _unavailable(
            f"the performance lane needs pycubrid and sqlalchemy-cubrid ({exc}); run make deps"
        )
    db = LiveDB(pycubrid)
    endpoint = "{host}:{port}/{database}".format(**DB_CONFIG)
    try:
        server = db.query("SELECT VERSION()")[0][0]
    except Exception as exc:  # any connect failure means "no database"
        _unavailable(f"no CUBRID at {endpoint} ({type(exc).__name__}: {exc}); run make up")
    versions = {
        "cubrid_server": server,
        "cubrid_endpoint": endpoint,
        "python": sys.version.split()[0],
        "pytest": pytest.__version__,
        "pycubrid": _version("pycubrid"),
        "sqlalchemy": _version("sqlalchemy"),
        "sqlalchemy_cubrid": _version("sqlalchemy-cubrid"),
    }
    for name, val in versions.items():
        record_testsuite_property(name, val)
    reporter = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            "performance lane environment: " + ", ".join(f"{k}={v}" for k, v in versions.items())
        )
    return db


@pytest.fixture(scope="session")
def sentinel_table(live_db: LiveDB) -> Iterator[tuple[str, list[tuple]]]:
    """An unrelated table that must survive every migration and benchmark script unchanged."""
    # A table name cannot be a `?` parameter; this one is generated here, never user input.
    table = f"cookbook_perf_sentinel_{uuid.uuid4().hex[:8]}"
    live_db.query(f"CREATE TABLE {table} (id INT PRIMARY KEY, label VARCHAR(40))")
    try:
        for row in [(1, "keep me"), (2, "untouched")]:
            live_db.query(f"INSERT INTO {table} (id, label) VALUES (?, ?)", row)
        yield table, live_db.query(f"SELECT id, label FROM {table} ORDER BY id")
    finally:
        live_db.query(f"DROP TABLE IF EXISTS {table}")


@pytest.fixture
def sentinel_unchanged(
    live_db: LiveDB, sentinel_table: tuple[str, list[tuple]], request: pytest.FixtureRequest
) -> Iterator[None]:
    """After each script-running test, check that the sentinel table is unchanged."""
    yield
    table, rows_before = sentinel_table
    try:
        rows_after = live_db.query(f"SELECT id, label FROM {table} ORDER BY id")
    except Exception as exc:  # e.g. the script dropped it
        pytest.fail(f"{request.node.name} broke unrelated table {table}: {exc}", pytrace=False)
    assert rows_after == rows_before, f"{request.node.name} changed unrelated table {table}"


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run under scripts/run_example.py (process-group kill on timeout), stderr merged."""
    result = subprocess.run(
        [sys.executable, str(RUN_EXAMPLE), "--timeout", str(timeout), "--", *command],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout + 30,
    )
    if result.returncode == 124 and "run_example: timed out after" in result.stdout:
        pytest.fail(f"{command[-1]} timed out after {timeout}s:\n{_tail(result.stdout)}")
    return result


def _tail(output: str, lines: int = 30) -> str:
    return "\n".join(output.splitlines()[-lines:])


def _run_benchmark(name: str, timeout: int) -> str:
    result = _run([sys.executable, str(PERFORMANCE_DIR / name / "benchmark.py")], timeout)
    output = result.stdout
    assert result.returncode == 0, f"{name} exited {result.returncode}:\n{_tail(output)}"
    assert output.strip(), f"{name} printed nothing"
    failure = FAILURE_PATTERN.search(output)
    assert failure is None, f"{name} printed {failure.group(0)!r}:\n{_tail(output)}"
    return output


def _match(output: str, pattern: str) -> re.Match[str]:
    match = re.search(pattern, output, re.MULTILINE)
    assert match, f"missing comparison line /{pattern}/ in output:\n{output}"
    return match


def _seconds(text: str) -> float:
    seconds = float(text)
    assert math.isfinite(seconds) and seconds >= 0, f"invalid time measurement: {text!r}"
    return seconds


def _assert_cleaned_up(live_db: LiveDB, table: str) -> None:
    assert not live_db.table_exists(table), f"{table} was left behind"


def _run_with_fault(live_db: LiveDB, name: str, fail_prefix: str, table: str) -> None:
    script = str(PERFORMANCE_DIR / name / "benchmark.py")
    result = _run([sys.executable, "-c", FAULT_RUNNER, script, fail_prefix, table], 120)
    output = result.stdout
    assert result.returncode != 0, f"injected failure was swallowed:\n{_tail(output)}"
    assert "RuntimeError: perf-fault injected failure" in output, _tail(output)
    assert f"perf-fault: {table} present at failure: 1" in output, _tail(output)
    _assert_cleaned_up(live_db, table)


class TestMigrationGoldens:
    """Java -> Python migration examples reproduce their golden output."""

    def test_all_five_golden_cases_are_collected(self) -> None:
        assert MIGRATION_CASES == [
            "01_connection",
            "02_crud_dbapi",
            "03_crud_orm",
            "04_transaction",
            "05_batch_operations",
        ]

    @pytest.mark.parametrize("case", MIGRATION_CASES)
    def test_migration_golden(self, case: str, live_db: LiveDB, sentinel_unchanged: None) -> None:
        result = _run([sys.executable, str(MIGRATION_DIR / f"{case}.py")], MIGRATION_TIMEOUT)
        assert result.returncode == 0, f"{case} exited {result.returncode}:\n{_tail(result.stdout)}"
        normalized = subprocess.run(
            ["bash", str(NORMALIZE)],
            input=result.stdout,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        expected = (MIGRATION_DIR / "expected" / f"{case}.expected").read_text()
        # `make verify` compares $(...) captures, which drop trailing newlines.
        assert normalized.rstrip("\n") == expected.rstrip("\n")


class TestPerformanceBenchmarks:
    """Benchmarks print a complete, parseable comparison and clean up after themselves."""

    def test_fetch_optimization_benchmark(self, live_db: LiveDB, sentinel_unchanged: None) -> None:
        output = _run_benchmark("fetch-optimization", timeout=300)
        _match(output, r"^Seeding complete\.$")
        _match(output, r"^=== Fetch Optimization Benchmark ===$")
        for label in (
            r"fetchone\(\) loop",
            r"fetchall\(\) \(all columns\)",
            r"fetchall\(\) \(specific columns\)",
            r"fetchmany\(500\) loop",
        ):
            match = _match(output, rf"^{label}:\s+{NUMBER}s\s+(\d+) rows$")
            _seconds(match.group(1))
            assert int(match.group(2)) == FETCH_ROWS, match.group(0)
        _assert_cleaned_up(live_db, "cookbook_fetch_test")

    def test_bulk_insert_benchmark(self, live_db: LiveDB, sentinel_unchanged: None) -> None:
        output = _run_benchmark("bulk-insert", timeout=600)
        _match(output, r"^=== Bulk Insert Benchmark ===$")
        for strategy, rows in BULK_ROWS.items():
            match = _match(
                output,
                rf"^Strategy {strategy} \([^)]+\):\s+{NUMBER}s\s+(\d+) rows\s+\((\d+) rows/sec\)$",
            )
            _seconds(match.group(1))
            assert int(match.group(2)) == rows, match.group(0)
        _match(output, r"^Key insight: one INSERT plus its own COMMIT takes ~\d+ms per row")
        _assert_cleaned_up(live_db, "cookbook_bulk_test")

    def test_connection_pooling_benchmark(self, live_db: LiveDB, sentinel_unchanged: None) -> None:
        output = _run_benchmark("connection-pooling", timeout=120)
        _match(output, r"^=== Connection Pooling Benchmark ===$")
        for label in (r"No pooling \(NullPool\)", r"Pooled \(pool_size=5\)"):
            match = _match(output, rf"^{label}:\s+{NUMBER}s total \({NUMBER}s per query\)$")
            _seconds(match.group(1))
            _seconds(match.group(2))
        _seconds(_match(output, rf"^Speedup factor:\s+{NUMBER}x$").group(1))
        match = _match(
            output,
            r"^Connections opened:\s+NullPool (\d+), pooled (\d+) \((\d+) queries each\)$",
        )
        no_pool, pooled, queries = (int(group) for group in match.groups())
        assert queries == POOL_QUERIES, match.group(0)
        assert no_pool == POOL_QUERIES, "NullPool must open one connection per query"
        assert 1 <= pooled <= POOL_SIZE, "the pool must reuse its connections"

    def test_fetch_optimization_cleans_up_when_it_raises(
        self, live_db: LiveDB, sentinel_unchanged: None
    ) -> None:
        _run_with_fault(live_db, "fetch-optimization", "INSERT", "cookbook_fetch_test")

    def test_bulk_insert_cleans_up_when_it_raises(
        self, live_db: LiveDB, sentinel_unchanged: None
    ) -> None:
        _run_with_fault(live_db, "bulk-insert", "DELETE", "cookbook_bulk_test")
