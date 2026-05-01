from __future__ import annotations

import time
import pycubrid


def main() -> None:
    """Benchmark three bulk insert strategies against CUBRID."""
    conn = None
    try:
        conn = pycubrid.connect(
            host="localhost",
            port=33000,
            database="testdb",
            user="dba",
            password="",
        )
        cursor = conn.cursor()

        # Create test table
        cursor.execute("DROP TABLE IF EXISTS cookbook_bulk_test")
        cursor.execute(
            """
            CREATE TABLE cookbook_bulk_test (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                val INT,
                is_active INT
            )
            """
        )
        conn.commit()

        num_rows = 5000

        # Strategy 1: Per-row COMMIT (reduced to 500 rows — full 5000 takes ~200s)
        per_row_count = 500
        cursor.execute("DELETE FROM cookbook_bulk_test")
        conn.commit()
        start = time.time()
        for i in range(per_row_count):
            cursor.execute(
                "INSERT INTO cookbook_bulk_test (name, val, is_active) VALUES (?, ?, ?)",
                (f"row_{i}", i, 1),
            )
            conn.commit()
        strategy1_time = time.time() - start
        strategy1_rows_sec = per_row_count / strategy1_time

        # Strategy 2: Batch COMMIT (every 500 rows)
        cursor.execute("DELETE FROM cookbook_bulk_test")
        conn.commit()
        start = time.time()
        for i in range(num_rows):
            cursor.execute(
                "INSERT INTO cookbook_bulk_test (name, val, is_active) VALUES (?, ?, ?)",
                (f"row_{i}", i, 1),
            )
            if (i + 1) % 500 == 0:
                conn.commit()
        conn.commit()
        strategy2_time = time.time() - start
        strategy2_rows_sec = num_rows / strategy2_time

        # Strategy 3: Single COMMIT at end
        cursor.execute("DELETE FROM cookbook_bulk_test")
        conn.commit()
        start = time.time()
        for i in range(num_rows):
            cursor.execute(
                "INSERT INTO cookbook_bulk_test (name, val, is_active) VALUES (?, ?, ?)",
                (f"row_{i}", i, 1),
            )
        conn.commit()
        strategy3_time = time.time() - start
        strategy3_rows_sec = num_rows / strategy3_time

        # Print results
        print("\n=== Bulk Insert Benchmark ===")
        print(f"Strategy 1 (per-row COMMIT):     {strategy1_time:.3f}s  {per_row_count} rows  ({strategy1_rows_sec:.0f} rows/sec)")
        print(f"Strategy 2 (batch COMMIT 500):   {strategy2_time:.3f}s  {num_rows} rows  ({strategy2_rows_sec:.0f} rows/sec)")
        print(f"Strategy 3 (single COMMIT):      {strategy3_time:.3f}s  {num_rows} rows  ({strategy3_rows_sec:.0f} rows/sec)")
        print(f"\nKey insight: COMMIT is ~{strategy1_time / per_row_count * 1000:.0f}ms per call — batch your writes!")
        print()

    finally:
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS cookbook_bulk_test")
                conn.commit()
            except Exception:
                pass
            conn.close()


if __name__ == "__main__":
    main()
