from __future__ import annotations

import time
import pycubrid


def main() -> None:
    """Benchmark fetch optimization strategies against CUBRID."""
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

        # Create test table with 10,000 rows
        cursor.execute("DROP TABLE IF EXISTS cookbook_fetch_test")
        cursor.execute(
            """
            CREATE TABLE cookbook_fetch_test (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                val INT,
                description VARCHAR(255),
                is_active INT
            )
            """
        )
        conn.commit()

        # Seed with 10,000 rows
        print("Seeding 10,000 rows...")
        for i in range(10000):
            cursor.execute(
                "INSERT INTO cookbook_fetch_test (name, val, description, is_active) VALUES (?, ?, ?, ?)",
                (f"row_{i}", i, f"Description for row {i}", 1),
            )
            if (i + 1) % 1000 == 0:
                conn.commit()
        conn.commit()
        print("Seeding complete.\n")

        # Benchmark 1: fetchone() loop
        start = time.time()
        cursor.execute("SELECT id, name, val, description, is_active FROM cookbook_fetch_test")
        rows_count = 0
        while True:
            row = cursor.fetchone()
            if row is None:
                break
            rows_count += 1
        fetchone_time = time.time() - start

        # Benchmark 2: fetchall()
        start = time.time()
        cursor.execute("SELECT id, name, val, description, is_active FROM cookbook_fetch_test")
        rows = cursor.fetchall()
        rows_count = len(rows)
        fetchall_time = time.time() - start

        # Benchmark 3: SELECT specific columns only
        start = time.time()
        cursor.execute("SELECT id, name FROM cookbook_fetch_test")
        rows = cursor.fetchall()
        rows_count = len(rows)
        specific_cols_time = time.time() - start

        # Benchmark 4: fetchmany() batches (all columns). SELECT * would be the
        # same query as benchmark 2, because the table has only these 5 columns.
        start = time.time()
        cursor.execute("SELECT id, name, val, description, is_active FROM cookbook_fetch_test")
        rows_count = 0
        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                break
            rows_count += len(batch)
        fetchmany_time = time.time() - start

        # Print results
        print("=== Fetch Optimization Benchmark ===")
        print(f"fetchone() loop:                 {fetchone_time:.3f}s")
        print(f"fetchall() (all columns):        {fetchall_time:.3f}s")
        print(f"fetchall() (specific columns):   {specific_cols_time:.3f}s")
        print(f"fetchmany(500) loop:             {fetchmany_time:.3f}s")
        print()

    finally:
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS cookbook_fetch_test")
                conn.commit()
            except Exception:
                pass
            conn.close()


if __name__ == "__main__":
    main()
