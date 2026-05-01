"""12_pool_retry_worker.py — Minimal connection pool and retry worker.

Demonstrates:
- Lightweight connection pool with borrow/return
- Retry wrapper with exponential backoff
- Replacing failed connections
- Background-like job processing with resilient DB access
"""

from __future__ import annotations

import datetime
import threading
import time

import pycubrid  # type: ignore[import-not-found]

CONNECT = getattr(pycubrid, "connect")
OPERATIONAL_ERROR = getattr(pycubrid, "OperationalError", Exception)
INTERFACE_ERROR = getattr(pycubrid, "InterfaceError", Exception)

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection():
    return CONNECT(**DB_CONFIG)


class ConnectionPool:
    """Minimal bounded connection pool (thread-safe)."""

    def __init__(self, size: int = 2) -> None:
        self._lock = threading.Lock()
        self._size = size
        self._connections = [get_connection() for _ in range(size)]

    def get(self):
        with self._lock:
            if not self._connections:
                return get_connection()
            return self._connections.pop()

    def put(self, conn) -> None:
        with self._lock:
            if len(self._connections) < self._size:
                self._connections.append(conn)
            else:
                # Pool is full — close the overflow connection
                try:
                    conn.close()
                except Exception:
                    pass

    def replace(self, bad_conn):
        try:
            bad_conn.close()
        except Exception:
            pass
        return get_connection()

    def health_check(self) -> None:
        with self._lock:
            healthy = 0
            unhealthy = 0
            refreshed = []
            for conn in self._connections:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    healthy += 1
                    refreshed.append(conn)
                except (OPERATIONAL_ERROR, INTERFACE_ERROR):
                    unhealthy += 1
                    refreshed.append(get_connection())
            self._connections = refreshed
        print(f"✓ Pool health check: healthy={healthy}, replaced={unhealthy}")

    def close_all(self) -> None:
        with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections = []


def run_with_retry(pool: ConnectionPool, fn, max_retries: int = 3):
    attempt = 0
    while True:
        conn = pool.get()
        try:
            result = fn(conn)
            pool.put(conn)
            return result
        except (OPERATIONAL_ERROR, INTERFACE_ERROR) as e:
            attempt += 1
            if attempt > max_retries:
                try:
                    conn.close()
                except Exception:
                    pass
                raise
            backoff = 0.1 * (2 ** (attempt - 1))
            print(
                f"  Retryable DB error: {type(e).__name__} (attempt {attempt}/{max_retries}), backoff={backoff:.2f}s"
            )
            replacement = pool.replace(conn)
            pool.put(replacement)
            time.sleep(backoff)


def setup_schema(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_jobs")
    cursor.execute("""
        CREATE TABLE cookbook_jobs (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            payload      VARCHAR(200) NOT NULL,
            status       VARCHAR(20) NOT NULL,
            attempts     INT DEFAULT 0,
            processed_at DATETIME,
            failed_once  INT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_jobs'")


def seed_jobs(conn) -> None:
    cursor = conn.cursor()
    jobs = [(f"job-{i}", "queued", 0, None, 0) for i in range(1, 6)]
    cursor.executemany(
        """
        INSERT INTO cookbook_jobs (payload, status, attempts, processed_at, failed_once)
        VALUES (?, ?, ?, ?, ?)
        """,
        jobs,
    )
    conn.commit()
    cursor.close()
    print("✓ Seeded 5 queued jobs")


def process_next_job(conn):
    """Pick and process ONE queued job atomically (single-worker safe)."""
    cursor = conn.cursor()
    # Atomic claim: UPDATE ... WHERE status='queued' LIMIT 1, then read back.
    # This prevents two workers from picking the same job.
    cursor.execute(
        """
        UPDATE cookbook_jobs SET status = 'processing'
        WHERE id = (
            SELECT id FROM cookbook_jobs WHERE status = 'queued' ORDER BY id LIMIT 1
        )
        """
    )
    if cursor.rowcount == 0:
        cursor.close()
        return None
    conn.commit()

    cursor.execute(
        """
        SELECT id, payload, attempts, failed_once
        FROM cookbook_jobs
        WHERE status = 'processing'
        ORDER BY id
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if row is None:
        cursor.close()
        return None

    job_id, payload, attempts, failed_once = row
    print(f"  Picked job id={job_id} payload={payload} attempts={attempts}")

    if failed_once == 0:
        cursor.execute(
            "UPDATE cookbook_jobs SET failed_once = 1, attempts = attempts + 1, status = 'queued' WHERE id = ?",
            (job_id,),
        )
        conn.commit()
        cursor.close()
        raise OPERATIONAL_ERROR(f"simulated transient failure for job {job_id}")

    finished_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    cursor.execute(
        """
        UPDATE cookbook_jobs
        SET status = 'done', attempts = attempts + 1, processed_at = ?
        WHERE id = ?
        """,
        (finished_at, job_id),
    )
    conn.commit()
    cursor.close()
    print(f"  ✓ Processed job id={job_id}")
    return job_id


def cleanup(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_jobs")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_jobs'")


if __name__ == "__main__":
    admin_conn = get_connection()
    pool = ConnectionPool(size=2)
    processed = 0

    try:
        setup_schema(admin_conn)
        seed_jobs(admin_conn)
        pool.health_check()

        while True:
            job_id = run_with_retry(pool, process_next_job, max_retries=3)
            if job_id is None:
                break
            processed += 1
            time.sleep(0.05)

        cursor = admin_conn.cursor()
        cursor.execute("SELECT id, payload, status, attempts FROM cookbook_jobs ORDER BY id")
        rows = cursor.fetchall()
        print("\n=== Job Results ===")
        for row in rows:
            print(f"  id={row[0]} payload={row[1]} status={row[2]} attempts={row[3]}")
        cursor.close()
        print(f"✓ Total processed jobs: {processed}")
    finally:
        cleanup(admin_conn)
        pool.close_all()
        admin_conn.close()
