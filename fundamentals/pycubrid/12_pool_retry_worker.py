"""12_pool_retry_worker.py — Minimal connection pool and retry worker.

Demonstrates:
- Lightweight connection pool with borrow/return
- Retry wrapper with exponential backoff
- Replacing failed connections
- Background-like job processing with resilient DB access
- A job claim that two workers cannot both win (conditional UPDATE + rowcount)
"""

from __future__ import annotations

import datetime
import threading
import time

import pycubrid  # type: ignore[import-not-found]

# Errors that mean a connection is broken or unreachable: the pool replaces
# the connection and run_with_retry() tries the job again. getattr() falls
# back to Exception if a driver build does not export one of these classes.
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
    return pycubrid.connect(**DB_CONFIG)


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
    cursor.execute("DROP TABLE IF EXISTS cookbook_retry_jobs")
    cursor.execute("""
        CREATE TABLE cookbook_retry_jobs (
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
    print("✓ Created table 'cookbook_retry_jobs'")


def seed_jobs(conn) -> None:
    cursor = conn.cursor()
    jobs = [(f"job-{i}", "queued", 0, None, 0) for i in range(1, 6)]
    cursor.executemany(
        """
        INSERT INTO cookbook_retry_jobs (payload, status, attempts, processed_at, failed_once)
        VALUES (?, ?, ?, ?, ?)
        """,
        jobs,
    )
    conn.commit()
    cursor.close()
    print("✓ Seeded 5 queued jobs")


def next_queued_id(cursor):
    cursor.execute("SELECT id FROM cookbook_retry_jobs WHERE status = 'queued' ORDER BY id LIMIT 1")
    row = cursor.fetchone()
    return None if row is None else row[0]


def try_claim(conn, cursor, job_id) -> bool:
    """Take ``job_id`` if it is still queued; return whether this worker got it.

    The status is checked in the UPDATE itself, so when two workers picked the same
    id only one changes the row (rowcount 1); the other sees rowcount 0.
    """
    cursor.execute(
        "UPDATE cookbook_retry_jobs SET status = 'processing' WHERE id = ? AND status = 'queued'",
        (job_id,),
    )
    claimed = cursor.rowcount == 1
    conn.commit()
    return claimed


def demo_claim_race() -> None:
    """Two workers read the same next job; only the first conditional claim wins."""
    worker_a, worker_b = get_connection(), get_connection()
    try:
        cur_a, cur_b = worker_a.cursor(), worker_b.cursor()
        job_a, job_b = next_queued_id(cur_a), next_queued_id(cur_b)
        print(f"  Worker A and worker B both read next job id={job_a} / id={job_b}")
        print(f"  Worker A claims id={job_a}: {try_claim(worker_a, cur_a, job_a)}")
        print(f"  Worker B claims id={job_b}: {try_claim(worker_b, cur_b, job_b)} (rowcount 0)")
        retry = next_queued_id(cur_b)
        print(f"  Worker B picks again: id={retry}")
        # Put the demo's job back so the pool below processes all five.
        cur_a.execute("UPDATE cookbook_retry_jobs SET status = 'queued' WHERE id = ?", (job_a,))
        worker_a.commit()
        cur_a.close()
        cur_b.close()
    finally:
        worker_a.close()
        worker_b.close()


def process_next_job(conn):
    """Claim and process ONE queued job; several workers never claim the same job."""
    cursor = conn.cursor()
    # Claim: pick the oldest queued id and take it with a conditional UPDATE; if
    # another worker took it first (rowcount 0), pick again.
    while True:
        candidate = next_queued_id(cursor)
        if candidate is None:
            conn.rollback()
            cursor.close()
            return None
        if try_claim(conn, cursor, candidate):
            break

    # Read back the claimed job by its id, not "any processing job".
    cursor.execute(
        "SELECT id, payload, attempts, failed_once FROM cookbook_retry_jobs WHERE id = ?",
        (candidate,),
    )
    job_id, payload, attempts, failed_once = cursor.fetchone()
    print(f"  Picked job id={job_id} payload={payload} attempts={attempts}")

    if failed_once == 0:
        cursor.execute(
            "UPDATE cookbook_retry_jobs SET failed_once = 1, attempts = attempts + 1, status = 'queued' WHERE id = ?",
            (job_id,),
        )
        conn.commit()
        cursor.close()
        raise OPERATIONAL_ERROR(f"simulated transient failure for job {job_id}")

    finished_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    cursor.execute(
        """
        UPDATE cookbook_retry_jobs
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
    cursor.execute("DROP TABLE IF EXISTS cookbook_retry_jobs")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_retry_jobs'")


if __name__ == "__main__":
    admin_conn = get_connection()
    pool = ConnectionPool(size=2)
    processed = 0

    try:
        setup_schema(admin_conn)
        seed_jobs(admin_conn)
        print("\n=== Claim race ===")
        demo_claim_race()
        print()
        pool.health_check()

        while True:
            job_id = run_with_retry(pool, process_next_job, max_retries=3)
            if job_id is None:
                break
            processed += 1
            time.sleep(0.05)

        cursor = admin_conn.cursor()
        cursor.execute("SELECT id, payload, status, attempts FROM cookbook_retry_jobs ORDER BY id")
        rows = cursor.fetchall()
        print("\n=== Job Results ===")
        for row in rows:
            print(f"  id={row[0]} payload={row[1]} status={row[2]} attempts={row[3]}")
        cursor.close()
        print(f"✓ Total processed jobs: {processed}")
    finally:
        # Close pool connections BEFORE dropping the table: a pooled connection
        # may still hold row locks on cookbook_retry_jobs from its last claim, and
        # DROP TABLE would block on those locks until the pool is closed.
        pool.close_all()
        cleanup(admin_conn)
        admin_conn.close()
