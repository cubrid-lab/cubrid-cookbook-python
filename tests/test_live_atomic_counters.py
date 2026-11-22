"""Opt-in live test: atomic counter increments from two independent connections (#628).

The lesson `fundamentals/pycubrid/13_atomic_counters.py` claims that
``INSERT ... ON DUPLICATE KEY UPDATE hit_count = hit_count + ?`` is atomic
per statement. Its own demo only sends events sequentially through one
cursor, so this probe exercises the claim the way a hot path actually uses
it: two independent connections incrementing the SAME counter key inside
two independent transactions, with the final total read from a third
connection.

Run it against a fresh, dedicated CUBRID 11.4 database:

    CUBRID_TEST_URL=cubrid+pycubrid://dba@localhost:33100/testdb \
        python -m pytest tests/test_live_atomic_counters.py -q

Without ``CUBRID_TEST_URL`` the live tests skip, so the offline lane
(``make check test``) stays green. A configured but unreachable database
fails instead of skipping. The probe uses its OWN table
(``cookbook_counters_concurrency``) — it never touches ``cookbook_counters``
or any other pre-existing object — and drops that table in ``finally`` even
when the probe raises. Synchronization is bounded (thread joins with a
timeout, a fixed number of retry attempts); there are no unbounded sleeps.

The offline sequencing twin lives in ``tests/test_atomic_counters_offline.py``;
its results validate the harness sequencing only and are NOT live CUBRID
evidence.
"""

from __future__ import annotations

import datetime
import os
import threading
import time
import uuid
from contextlib import closing
from typing import Any, Callable
from urllib.parse import urlsplit

import pytest

PROBE_TABLE = "cookbook_counters_concurrency"
PER_CONNECTION_INCREMENTS = 50
MAX_ATTEMPTS = 3
JOIN_TIMEOUT_S = 60.0

CREATE_PROBE_TABLE = f"""
    CREATE TABLE {PROBE_TABLE} (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        metric_key VARCHAR(120) NOT NULL,
        metric_day DATE NOT NULL,
        hit_count  INT NOT NULL DEFAULT 0,
        UNIQUE (metric_key, metric_day)
    )
"""

INCREMENT = f"""
    INSERT INTO {PROBE_TABLE} (metric_key, metric_day, hit_count)
    VALUES (?, ?, ?)
    ON DUPLICATE KEY UPDATE hit_count = hit_count + ?
"""


def probe_settings() -> dict[str, Any]:
    """Parse CUBRID_TEST_URL into pycubrid.connect kwargs; fail closed."""
    url = os.environ.get("CUBRID_TEST_URL")
    if not url:
        pytest.skip("CUBRID_TEST_URL is not set; live atomic-counter probe skipped")
    import pycubrid  # type: ignore[import-not-found]

    parts = urlsplit(url)
    if parts.scheme != "cubrid+pycubrid":
        pytest.fail(f"CUBRID_TEST_URL must be cubrid+pycubrid://..., got {url!r}", pytrace=False)
    settings = {
        "host": parts.hostname or "localhost",
        "port": parts.port or 33000,
        "database": parts.path.lstrip("/"),
        "user": parts.username or "dba",
        "password": parts.password or "",
    }
    try:
        with closing(pycubrid.connect(**settings, connect_timeout=10)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT 1 FROM db_root")
                assert cursor.fetchone()[0] == 1
    except Exception as exc:
        pytest.fail(f"CUBRID_TEST_URL is set but CUBRID is unreachable: {exc}", pytrace=False)
    return settings


def run_probe(
    connect: Callable[[], Any],
    key: str,
    day: datetime.date,
    per_connection: int = PER_CONNECTION_INCREMENTS,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Seed one test-owned counter key, hammer it from two connections, read back.

    `connect` opens one independent connection per call. Returns a report
    dict {final, expected, attempts, errors}; raises the last error when no
    attempt succeeded. The probe table is dropped in `finally` regardless.
    """
    # Setup on its own connection: fresh test-owned table + one seeded row.
    with closing(connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
            cursor.execute(CREATE_PROBE_TABLE)
            cursor.execute(
                f"INSERT INTO {PROBE_TABLE} (metric_key, metric_day, hit_count) VALUES (?, ?, 0)",
                (key, day),
            )
        conn.commit()

    report: dict[str, Any] = {
        "final": None,
        "expected": 2 * per_connection,
        "attempts": 0,
        "errors": [],
    }
    try:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            report["attempts"] = attempt
            errors: list[str] = []
            done = threading.Event()

            def worker() -> None:
                try:
                    with closing(connect()) as conn:
                        with closing(conn.cursor()) as cursor:
                            for _ in range(per_connection):
                                cursor.execute(INCREMENT, (key, day, 1, 1))
                        conn.commit()
                except Exception as exc:  # lock timeout / deadlock surface here
                    errors.append(f"{type(exc).__name__}: {exc}")
                finally:
                    done.set()

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            # Bounded wait: never hang on an interleaving the server disallows.
            deadline = time.monotonic() + JOIN_TIMEOUT_S
            for t in threads:
                t.join(timeout=max(0.0, deadline - time.monotonic()))
            if any(t.is_alive() for t in threads):
                report["errors"].append(f"lock wait exceeded {JOIN_TIMEOUT_S}s bound")
                last_error = RuntimeError("worker thread did not finish within the bound")
                continue
            if errors:
                report["errors"].extend(errors)
                last_error = RuntimeError("; ".join(errors))
                continue  # bounded retry
            # Third connection reads the final committed total.
            with closing(connect()) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute(
                        f"SELECT hit_count FROM {PROBE_TABLE} WHERE metric_key = ? AND metric_day = ?",
                        (key, day),
                    )
                    row = cursor.fetchone()
            report["final"] = row[0] if row else None
            return report
        raise last_error if last_error else RuntimeError("probe failed without an error")
    finally:
        with closing(connect()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
            conn.commit()


@pytest.fixture
def settings() -> dict[str, Any]:
    return probe_settings()


def test_two_connections_never_lose_an_increment(settings):
    import pycubrid  # type: ignore[import-not-found]

    connect = lambda: pycubrid.connect(**settings, connect_timeout=10)  # noqa: E731
    key = f"probe-{uuid.uuid4().hex}"
    day = datetime.datetime.now(datetime.timezone.utc).date()
    report = run_probe(connect, key, day)
    print(f"\nlive probe outcome: {report}")
    assert report["errors"] == [], f"probe hit errors: {report['errors']}"
    assert report["final"] == report["expected"], (
        f"lost updates: final={report['final']} expected={report['expected']} attempts={report['attempts']}"
    )


def test_probe_table_is_torn_down(settings):
    import pycubrid  # type: ignore[import-not-found]

    connect = lambda: pycubrid.connect(**settings, connect_timeout=10)  # noqa: E731
    key = f"probe-{uuid.uuid4().hex}"
    day = datetime.datetime.now(datetime.timezone.utc).date()
    run_probe(connect, key, day)
    with closing(connect()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                (PROBE_TABLE.upper(),),
            )
            assert cursor.fetchone()[0] == 0, "probe table must be dropped after the run"
