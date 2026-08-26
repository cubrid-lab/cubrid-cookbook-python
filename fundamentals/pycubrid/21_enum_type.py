"""21_enum_type.py - The ENUM column type.

Demonstrates:
- Declaring an ENUM column with an ordered set of allowed string values
- Ordering by an ENUM sorts by DECLARATION order, not alphabetically
- Recovering the 1-based ordinal of a value with `col + 0`
- Rejecting a value outside the declared set

The declaration order IS the sort/priority order, which makes ENUM a compact
way to model ranked categorical values (priority, severity, size, ...).
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

import pycubrid


DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_tickets")
    cursor.execute(
        """
        CREATE TABLE cookbook_tickets (
            id       INT PRIMARY KEY,
            title    VARCHAR(40) NOT NULL,
            priority ENUM('low', 'medium', 'high', 'critical') NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_tickets'")


def seed_tickets(cursor):
    rows = [
        (1, "Typo in footer", "low"),
        (2, "Login sometimes fails", "high"),
        (3, "DB is down", "critical"),
        (4, "Slow dashboard", "medium"),
    ]
    cursor.executemany(
        "INSERT INTO cookbook_tickets (id, title, priority) VALUES (?, ?, ?)",
        rows,
    )
    print(f"✓ Inserted tickets: {len(rows)}")


def order_by_enum(cursor):
    # ORDER BY priority uses declaration order: low < medium < high < critical.
    cursor.execute(
        """
        SELECT id, title, priority, priority + 0 AS ordinal
          FROM cookbook_tickets
         ORDER BY priority DESC, id
        """
    )
    print("\nTickets by priority (highest first):")
    print("  ordinal  priority  title")
    for _id, title, priority, ordinal in cursor.fetchall():
        print(f"  {ordinal:>7}  {priority:<8}  {title}")


def reject_invalid(cursor, conn):
    print("\nInserting an out-of-set value ('urgent'):")
    try:
        cursor.execute(
            "INSERT INTO cookbook_tickets (id, title, priority) VALUES (?, ?, ?)",
            (99, "Bad value", "urgent"),
        )
        conn.commit()
        print("  (unexpected) insert succeeded")
    except pycubrid.DatabaseError as exc:
        conn.rollback()
        print(f"  rejected by ENUM constraint: {type(exc).__name__}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_tickets")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_tickets'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()
        seed_tickets(cursor)
        conn.commit()
        order_by_enum(cursor)
        reject_invalid(cursor, conn)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
