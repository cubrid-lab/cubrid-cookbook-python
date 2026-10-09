"""05_batch_operations.py — Batch operations: Java addBatch/executeBatch → Python executemany.

Migration from Java's verbose batch pattern to Python's one-liner.

Java JDBC batch pattern (what you're replacing):
────────────────────────────────────────────────
    PreparedStatement ps = conn.prepareStatement(
        "INSERT INTO cookbook_sensors (val, cnt) VALUES (?, ?)"
    );
    for (String[] row : data) {
        ps.setString(1, row[0]);
        ps.setInt(2, Integer.parseInt(row[1]));
        ps.addBatch();
    }
    int[] results = ps.executeBatch();
    conn.commit();

Python pycubrid (what you'll write):
─────────────────────────────────────
    cursor.executemany(
        "INSERT INTO cookbook_sensors (val, cnt) VALUES (?, ?)",
        data,
    )
    conn.commit()

No addBatch loop. No type casting. One call.

Performance note from our benchmarks:
    COMMIT is the dominant cost (INSERT + COMMIT ~36 ms per row on pycubrid 1.10.0).
    For bulk writes, batch your inserts and commit once at the end.
"""

from __future__ import annotations

import time

import pycubrid

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection() -> pycubrid.Connection:
    return pycubrid.connect(**DB_CONFIG)


def setup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_sensors")
    cursor.execute("""
        CREATE TABLE cookbook_sensors (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            val       VARCHAR(100) NOT NULL,
            cnt       INT DEFAULT 0,
            file_data VARCHAR(500)
        )
    """)
    conn.commit()
    cursor.close()


def batch_insert_executemany(conn: pycubrid.Connection) -> None:
    """Batch INSERT using executemany.

    Java equivalent (addBatch/executeBatch):
        PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO cookbook_sensors (val, cnt, file_data) VALUES (?, ?, ?)"
        );
        for (Object[] row : sensorData) {
            ps.setString(1, (String) row[0]);
            ps.setInt(2, (Integer) row[1]);
            ps.setString(3, (String) row[2]);
            ps.addBatch();
            if (i % batchSize == 0) {
                ps.executeBatch();
                conn.commit();
            }
        }
        ps.executeBatch();
        conn.commit();

    Python — executemany handles the loop internally:
    """
    sensor_data = [(f"sensor_{i:04d}", i % 100, f"reading_{i}") for i in range(1000)]

    cursor = conn.cursor()

    t0 = time.perf_counter()
    cursor.executemany(
        "INSERT INTO cookbook_sensors (val, cnt, file_data) VALUES (?, ?, ?)",
        sensor_data,
    )
    conn.commit()
    elapsed = time.perf_counter() - t0

    print(f"executemany: inserted {len(sensor_data)} rows in {elapsed * 1000:.1f}ms")
    cursor.close()


def batch_insert_chunked(conn: pycubrid.Connection) -> None:
    """Chunked batch insert for very large datasets.

    Java equivalent:
        int batchSize = 500;
        int count = 0;
        for (Object[] row : hugeDataset) {
            ps.setString(1, ...);
            ps.addBatch();
            if (++count % batchSize == 0) {
                ps.executeBatch();
                conn.commit();
            }
        }
        ps.executeBatch();
        conn.commit();

    Python — chunk with slicing, commit per chunk:
    """
    rows = [(f"bulk_{i:05d}", i % 256, f"data_{i}") for i in range(2000)]

    chunk_size = 500
    cursor = conn.cursor()

    t0 = time.perf_counter()
    for offset in range(0, len(rows), chunk_size):
        chunk = rows[offset : offset + chunk_size]
        cursor.executemany(
            "INSERT INTO cookbook_sensors (val, cnt, file_data) VALUES (?, ?, ?)",
            chunk,
        )
        conn.commit()
    elapsed = time.perf_counter() - t0

    print(f"chunked ({chunk_size}/commit): inserted {len(rows)} rows in {elapsed * 1000:.1f}ms")
    cursor.close()


def batch_insert_single_commit(conn: pycubrid.Connection) -> None:
    """Single-commit batch for maximum throughput.

    COMMIT is the most expensive operation (pycubrid 1.10.0 benchmarks).
    Minimizing commits maximizes throughput for trusted data.

    Trade-off: If insertion fails mid-batch, all rows roll back.
    """
    rows = [(f"fast_{i:05d}", i % 256, f"data_{i}") for i in range(2000)]

    cursor = conn.cursor()

    t0 = time.perf_counter()
    cursor.executemany(
        "INSERT INTO cookbook_sensors (val, cnt, file_data) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    elapsed = time.perf_counter() - t0

    print(f"single commit: inserted {len(rows)} rows in {elapsed * 1000:.1f}ms")
    cursor.close()


def batch_update(conn: pycubrid.Connection) -> None:
    """Batch UPDATE using executemany.

    Java:
        PreparedStatement ps = conn.prepareStatement(
            "UPDATE cookbook_sensors SET cnt = ? WHERE val = ?"
        );
        for (Object[] update : updates) {
            ps.setInt(1, (Integer) update[0]);
            ps.setString(2, (String) update[1]);
            ps.addBatch();
        }
        ps.executeBatch();
        conn.commit();

    Python — same executemany, works for UPDATE too:
    """
    updates = [(999, f"sensor_{i:04d}") for i in range(0, 100, 10)]

    cursor = conn.cursor()
    cursor.executemany(
        "UPDATE cookbook_sensors SET cnt = ? WHERE val = ?",
        updates,
    )
    conn.commit()
    print(f"batch update: updated {len(updates)} rows")
    cursor.close()


def batch_delete(conn: pycubrid.Connection) -> None:
    """Batch DELETE — single statement with IN clause.

    Java:
        // Option 1: Batch with PreparedStatement
        PreparedStatement ps = conn.prepareStatement(
            "DELETE FROM cookbook_sensors WHERE val = ?"
        );
        for (String name : toDelete) {
            ps.setString(1, name);
            ps.addBatch();
        }
        ps.executeBatch();

        // Option 2: Single DELETE with IN (more efficient)
        stmt.executeUpdate("DELETE FROM cookbook_sensors WHERE cnt = 999");

    Python — single WHERE is usually faster than batch DELETE:
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cookbook_sensors WHERE cnt = ?", (999,))
    conn.commit()
    print(f"batch delete: removed {cursor.rowcount} rows (WHERE cnt=999)")
    cursor.close()


def verify_counts(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cookbook_sensors")
    total = cursor.fetchone()[0]
    print(f"\nTotal rows remaining: {total}")
    cursor.close()


def cleanup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_sensors")
    conn.commit()
    cursor.close()
    print("Cleaned up")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup(conn)

        print("=== Batch INSERT ===")
        batch_insert_executemany(conn)

        print("\n=== Batch UPDATE ===")
        batch_update(conn)

        print("\n=== Batch DELETE ===")
        batch_delete(conn)

        verify_counts(conn)

        print("\n=== Batch INSERT (chunked) ===")
        setup(conn)
        batch_insert_chunked(conn)

        print("\n=== Batch INSERT (single commit) ===")
        setup(conn)
        batch_insert_single_commit(conn)
    finally:
        cleanup(conn)
        conn.close()
