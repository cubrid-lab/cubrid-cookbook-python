"""15_cursor_memory_bound.py - Bounded memory fetching with connection fetch_size.

Demonstrates:
- Setting ``fetch_size`` at connection level to cap server fetch page size
- Measuring peak client memory with ``tracemalloc`` across fetch_size values
- How fetch_size differs from cursor.arraysize (page size vs client batch)

``fetch_size`` (new in pycubrid 1.6) is the page size the driver requests
from the CAS broker when fetching rows from a result set. Smaller pages mean
lower peak memory but more round-trips; larger pages mean fewer round-trips
but more memory. ``arraysize`` only controls how many rows ``fetchmany()``
returns to your application — it does NOT change how the driver pages rows
from the server.

Run:
    python 15_cursor_memory_bound.py
"""

from __future__ import annotations

import tracemalloc
from typing import Any

import pycubrid  # type: ignore[import-not-found]
from pycubrid import DatabaseError  # type: ignore[import-not-found]

DB_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}

ROW_COUNT = 5_000


def get_connection(fetch_size: int) -> Any:
    """Open a connection with a specific server-side fetch page size."""
    return pycubrid.connect(**DB_CONFIG, fetch_size=fetch_size)


def setup_schema(conn: Any) -> None:
    """Create a table and seed it with ROW_COUNT wide rows."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_fetch_probe")
    cur.execute(
        """
        CREATE TABLE cookbook_fetch_probe (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            payload      VARCHAR(400) NOT NULL,
            created_at   DATETIME NOT NULL
        )
        """
    )
    # Seed rows in batches of 500 using parameterized qmark queries.
    insert_sql = "INSERT INTO cookbook_fetch_probe (payload, created_at) VALUES (?, ?)"
    batch: list[tuple[str, str]] = []
    seeded = 0
    while seeded < ROW_COUNT:
        rows_this_batch = min(500, ROW_COUNT - seeded)
        batch = [
            (f"row-{seeded + i:06d}-" + ("x" * 380), "2026-01-01 00:00:00")
            for i in range(rows_this_batch)
        ]
        cur.executemany(insert_sql, batch)
        seeded += rows_this_batch
    conn.commit()
    cur.close()
    print(f"[setup] Seeded {ROW_COUNT} rows into cookbook_fetch_probe")


def measure_peak_memory(fetch_size: int) -> tuple[int, float]:
    """Return (peak_bytes, total_seconds) for a full table scan at fetch_size."""
    conn = get_connection(fetch_size)
    cur = conn.cursor()
    tracemalloc.start()
    cur.execute("SELECT id, payload, created_at FROM cookbook_fetch_probe")
    rows = cur.fetchall()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cur.close()
    conn.close()
    if len(rows) != ROW_COUNT:
        raise RuntimeError(f"expected {ROW_COUNT} rows, got {len(rows)}")
    return peak, 0.0


def main() -> None:
    print("=== Cursor Memory Bounding Demo (pycubrid 1.6+) ===")
    print()

    # Seed once using the default fetch_size.
    seed_conn = get_connection(fetch_size=100)
    try:
        setup_schema(seed_conn)
    finally:
        seed_conn.close()

    print()
    print(f"Comparing peak client memory for a full table scan of {ROW_COUNT} wide rows:")
    print()

    results: list[tuple[int, int]] = []
    for fs in (10, 100, 1000):
        peak_bytes, _ = measure_peak_memory(fs)
        results.append((fs, peak_bytes))
        print(f"  fetch_size={fs:5d}  peak_memory={peak_bytes / 1024:8.1f} KB")

    smallest_peak = min(p for _, p in results)
    largest_peak = max(p for _, p in results)
    if largest_peak > 0:
        ratio = largest_peak / smallest_peak
        print()
        print(f"Peak memory ratio (largest / smallest): {ratio:.1f}x")
        print()
        print("Key takeaway: smaller fetch_size caps peak client memory at the")
        print("cost of more round-trips. Choose a fetch_size that matches your")
        print("expected working set and broker latency.")

    print()
    print("--- fetch_size vs arraysize ---")
    print("  fetch_size: server page size (connection-level, set via connect())")
    print("  arraysize:  client batch size for cursor.fetchmany() (per-cursor)")
    print("  They are INDEPENDENT. fetch_size governs network/memory paging;")
    print("  arraysize governs how many rows fetchmany() returns per call.")


if __name__ == "__main__":
    try:
        main()
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
