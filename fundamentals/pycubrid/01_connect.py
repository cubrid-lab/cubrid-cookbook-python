"""01_connect.py — Connecting to CUBRID with pycubrid.

Demonstrates:
- Basic connection
- Running a simple query
- Using cursor.description for column metadata
- Connection as context manager
"""

from __future__ import annotations

import pycubrid


def basic_connection() -> None:
    """Connect, query, disconnect."""
    conn = pycubrid.connect(
        host="localhost",
        port=33000,
        database="testdb",
        user="dba",
        password="",
    )

    cursor = conn.cursor()
    cursor.execute("SELECT 1 + 1 AS result")

    row = cursor.fetchone()
    print(f"1 + 1 = {row[0]}")

    cursor.close()
    conn.close()


def connection_info() -> None:
    """Inspect connection metadata."""
    conn = pycubrid.connect(
        host="localhost",
        port=33000,
        database="testdb",
        user="dba",
    )

    cursor = conn.cursor()

    # Server version
    cursor.execute("SELECT version()")
    version = cursor.fetchone()
    print(f"CUBRID version: {version[0]}")

    # Current database
    cursor.execute("SELECT database()")
    db = cursor.fetchone()
    print(f"Database: {db[0]}")

    # Current user
    cursor.execute("SELECT user()")
    user = cursor.fetchone()
    print(f"User: {user[0]}")

    cursor.close()
    conn.close()


def cursor_description() -> None:
    """Use cursor.description to inspect result columns."""
    conn = pycubrid.connect(
        host="localhost",
        port=33000,
        database="testdb",
        user="dba",
    )

    cursor = conn.cursor()
    cursor.execute("SELECT 1 AS id, 'hello' AS name, CAST(3.14 AS DOUBLE) AS val")

    # cursor.description: list of (name, type_code, display_size, internal_size,
    #                               precision, scale, null_ok)
    if cursor.description:
        print("Columns:")
        for col in cursor.description:
            print(f"  {col[0]:10s}  type_code={col[1]}")

    row = cursor.fetchone()
    print(f"Row: {row}")

    cursor.close()
    conn.close()


def multiple_queries() -> None:
    """Run multiple queries on the same connection."""
    conn = pycubrid.connect(
        host="localhost",
        port=33000,
        database="testdb",
        user="dba",
    )

    cursor = conn.cursor()

    queries = [
        "SELECT 1 AS a",
        "SELECT 'hello' AS b",
        "SELECT CURRENT_DATE AS today",
    ]

    for sql in queries:
        cursor.execute(sql)
        row = cursor.fetchone()
        print(f"{sql:40s} → {row[0]}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    print("=== Basic Connection ===")
    basic_connection()

    print("\n=== Connection Info ===")
    connection_info()

    print("\n=== Cursor Description ===")
    cursor_description()

    print("\n=== Multiple Queries ===")
    multiple_queries()
