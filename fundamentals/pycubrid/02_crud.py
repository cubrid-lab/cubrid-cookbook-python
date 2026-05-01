"""02_crud.py — CRUD operations with pycubrid.

Demonstrates:
- CREATE TABLE
- INSERT rows
- SELECT with filtering
- UPDATE rows
- DELETE rows
- DROP TABLE cleanup
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


def setup_table(conn: pycubrid.Connection) -> None:
    """Create the example table."""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_users")
    cursor.execute("""
        CREATE TABLE cookbook_users (
            id    INT AUTO_INCREMENT PRIMARY KEY,
            name  VARCHAR(100) NOT NULL,
            email VARCHAR(200) UNIQUE,
            age   INT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_users'")


def insert_rows(conn: pycubrid.Connection) -> None:
    """INSERT — add rows to the table."""
    cursor = conn.cursor()

    # Single insert with parameters
    cursor.execute(
        "INSERT INTO cookbook_users (name, email, age) VALUES (?, ?, ?)",
        ("Alice", "alice@example.com", 30),
    )

    # Multiple inserts
    users = [
        ("Bob", "bob@example.com", 25),
        ("Charlie", "charlie@example.com", 35),
        ("Diana", "diana@example.com", 28),
        ("Eve", "eve@example.com", 32),
    ]
    cursor.executemany(
        "INSERT INTO cookbook_users (name, email, age) VALUES (?, ?, ?)",
        users,
    )

    conn.commit()
    cursor.close()
    print(f"✓ Inserted {1 + len(users)} rows")


def select_all(conn: pycubrid.Connection) -> None:
    """SELECT — read all rows."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, age FROM cookbook_users ORDER BY id")

    rows = cursor.fetchall()
    print(f"\nAll users ({len(rows)} rows):")
    print(f"  {'ID':>3s}  {'Name':12s}  {'Email':25s}  {'Age':>3s}")
    print(f"  {'---':>3s}  {'----':12s}  {'-----':25s}  {'---':>3s}")
    for row in rows:
        print(f"  {row[0]:3d}  {row[1]:12s}  {row[2]:25s}  {row[3]:3d}")

    cursor.close()


def select_filtered(conn: pycubrid.Connection) -> None:
    """SELECT with WHERE clause and parameters."""
    cursor = conn.cursor()

    # Filter by age
    cursor.execute(
        "SELECT name, age FROM cookbook_users WHERE age >= ? ORDER BY age DESC",
        (30,),
    )
    rows = cursor.fetchall()
    print(f"\nUsers age >= 30 ({len(rows)} rows):")
    for row in rows:
        print(f"  {row[0]:12s}  age={row[1]}")

    # Filter by name pattern
    cursor.execute(
        "SELECT name, email FROM cookbook_users WHERE name LIKE ?",
        ("%li%",),
    )
    rows = cursor.fetchall()
    print(f"\nUsers with 'li' in name ({len(rows)} rows):")
    for row in rows:
        print(f"  {row[0]:12s}  {row[1]}")

    cursor.close()


def select_with_fetch_methods(conn: pycubrid.Connection) -> None:
    """Demonstrate fetchone, fetchmany, fetchall."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM cookbook_users ORDER BY id")

    # fetchone — one row at a time
    first = cursor.fetchone()
    print(f"\nfetchone():  {first[0]}")

    # fetchmany — batch of rows
    batch = cursor.fetchmany(2)
    print(f"fetchmany(2): {[r[0] for r in batch]}")

    # fetchall — remaining rows
    rest = cursor.fetchall()
    print(f"fetchall():  {[r[0] for r in rest]}")

    cursor.close()


def update_rows(conn: pycubrid.Connection) -> None:
    """UPDATE — modify existing rows."""
    cursor = conn.cursor()

    # Update single row
    cursor.execute(
        "UPDATE cookbook_users SET age = ? WHERE name = ?",
        (31, "Alice"),
    )
    print(f"\n✓ Updated Alice's age (rows affected: {cursor.rowcount})")

    # Update multiple rows
    cursor.execute(
        "UPDATE cookbook_users SET age = age + 1 WHERE age < ?",
        (30,),
    )
    print(f"✓ Incremented age for young users (rows affected: {cursor.rowcount})")

    conn.commit()
    cursor.close()


def delete_rows(conn: pycubrid.Connection) -> None:
    """DELETE — remove rows."""
    cursor = conn.cursor()

    cursor.execute("DELETE FROM cookbook_users WHERE name = ?", ("Eve",))
    print(f"\n✓ Deleted Eve (rows affected: {cursor.rowcount})")

    conn.commit()
    cursor.close()


def cleanup(conn: pycubrid.Connection) -> None:
    """Drop the example table."""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_users")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_users'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_table(conn)
        insert_rows(conn)
        select_all(conn)
        select_filtered(conn)
        select_with_fetch_methods(conn)
        update_rows(conn)
        select_all(conn)  # Show updated state
        delete_rows(conn)
        select_all(conn)  # Show final state
    finally:
        cleanup(conn)
        conn.close()
