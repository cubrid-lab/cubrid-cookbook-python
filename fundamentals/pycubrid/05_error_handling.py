"""05_error_handling.py — Exception handling with pycubrid.

Demonstrates:
- PEP 249 exception hierarchy
- Catching specific database errors
- Handling connection failures
- Graceful error recovery
"""

from __future__ import annotations

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


def exception_hierarchy() -> None:
    """PEP 249 exception hierarchy in pycubrid.

    Exception
    ├── Warning
    └── Error
        ├── InterfaceError      — driver/connection issues
        └── DatabaseError       — database-side errors
            ├── DataError           — bad data values
            ├── OperationalError    — operational failures
            ├── IntegrityError      — constraint violations
            ├── InternalError       — internal DB errors
            ├── ProgrammingError    — SQL syntax errors, bad table names
            └── NotSupportedError   — unsupported features
    """
    print("=== PEP 249 Exception Hierarchy ===")
    print("  Exception")
    print("  ├── Warning")
    print("  └── Error")
    print("      ├── InterfaceError")
    print("      └── DatabaseError")
    print("          ├── DataError")
    print("          ├── OperationalError")
    print("          ├── IntegrityError")
    print("          ├── InternalError")
    print("          ├── ProgrammingError")
    print("          └── NotSupportedError")

    # All exception classes are importable from pycubrid
    assert issubclass(pycubrid.InterfaceError, pycubrid.Error)
    assert issubclass(pycubrid.DatabaseError, pycubrid.Error)
    assert issubclass(pycubrid.IntegrityError, pycubrid.DatabaseError)
    assert issubclass(pycubrid.ProgrammingError, pycubrid.DatabaseError)
    print("  ✓ Hierarchy verified")


def connection_error_example() -> None:
    """Handle connection failures gracefully."""
    print("\n=== Connection Error Handling ===")

    # Wrong host
    try:
        pycubrid.connect(host="nonexistent-host", port=33000, database="testdb")
    except pycubrid.OperationalError as e:
        print(f"  ✓ Caught OperationalError (bad host): {e}")

    # Wrong port
    try:
        pycubrid.connect(host="localhost", port=44444, database="testdb")
    except (
        pycubrid.OperationalError,
        pycubrid.InterfaceError,
        OSError,
        ConnectionRefusedError,
    ) as e:
        print(f"  ✓ Caught connection error (bad port): {type(e).__name__}: {e}")


def syntax_error_example() -> None:
    """ProgrammingError — SQL syntax errors."""
    print("\n=== SQL Syntax Errors ===")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELEC * FORM nonexistent_table")
    except pycubrid.ProgrammingError as e:
        print(f"  ✓ Caught ProgrammingError (bad SQL): {e}")

    cursor.close()
    conn.close()


def integrity_error_example() -> None:
    """IntegrityError — constraint violations."""
    print("\n=== Integrity Errors ===")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS cookbook_err_test")
    cursor.execute("""
        CREATE TABLE cookbook_err_test (
            id    INT PRIMARY KEY,
            email VARCHAR(200) UNIQUE
        )
    """)
    cursor.execute("INSERT INTO cookbook_err_test (id, email) VALUES (1, 'a@test.com')")
    conn.commit()

    # Duplicate primary key
    try:
        cursor.execute("INSERT INTO cookbook_err_test (id, email) VALUES (1, 'b@test.com')")
    except pycubrid.IntegrityError as e:
        conn.rollback()
        print(f"  ✓ Caught IntegrityError (duplicate PK): {e}")

    # Duplicate unique constraint
    try:
        cursor.execute("INSERT INTO cookbook_err_test (id, email) VALUES (2, 'a@test.com')")
    except pycubrid.IntegrityError as e:
        conn.rollback()
        print(f"  ✓ Caught IntegrityError (duplicate UNIQUE): {e}")

    cursor.execute("DROP TABLE IF EXISTS cookbook_err_test")
    conn.commit()
    cursor.close()
    conn.close()


def error_recovery_pattern() -> None:
    """Pattern: try/except with rollback for safe error recovery."""
    print("\n=== Error Recovery Pattern ===")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS cookbook_orders")
    cursor.execute("""
        CREATE TABLE cookbook_orders (
            id     INT AUTO_INCREMENT PRIMARY KEY,
            item   VARCHAR(100),
            amount DOUBLE NOT NULL
        )
    """)
    conn.commit()

    # Batch of operations — some may fail
    orders = [
        ("Widget", 10.00),
        ("Gadget", 25.00),
        (None, -1.0),  # This might cause issues
        ("Doohickey", 15.00),
    ]

    successful = 0
    failed = 0

    for item, amount in orders:
        try:
            cursor.execute(
                "INSERT INTO cookbook_orders (item, amount) VALUES (?, ?)",
                (item, amount),
            )
            conn.commit()
            successful += 1
        except pycubrid.Error as e:
            conn.rollback()
            failed += 1
            print(f"  ⚠ Failed to insert ({item}, {amount}): {e}")

    print(f"  ✓ Results: {successful} succeeded, {failed} failed")

    cursor.execute("SELECT item, amount FROM cookbook_orders ORDER BY id")
    for row in cursor.fetchall():
        print(f"    {row[0]}: ${row[1]:.2f}")

    cursor.execute("DROP TABLE IF EXISTS cookbook_orders")
    conn.commit()
    cursor.close()
    conn.close()


def using_generic_error_catch() -> None:
    """Catch all database errors with the base Error class."""
    print("\n=== Generic Error Catching ===")
    conn = get_connection()
    cursor = conn.cursor()

    operations = [
        "SELECT 1",
        "SELECT * FROM this_table_does_not_exist",
        "INVALID SQL SYNTAX HERE",
    ]

    for sql in operations:
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            print(f"  ✓ '{sql[:40]}' → {row}")
        except pycubrid.Error as e:
            # pycubrid.Error catches all DB-related exceptions
            print(f"  ✗ '{sql[:40]}' → {type(e).__name__}: {e}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    exception_hierarchy()
    connection_error_example()
    syntax_error_example()
    integrity_error_example()
    error_recovery_pattern()
    using_generic_error_catch()
