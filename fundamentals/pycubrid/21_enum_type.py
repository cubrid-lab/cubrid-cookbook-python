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


# CUBRID reports a bound value that cannot be converted to the column type as error -494
# (pycubrid raises ProgrammingError) with the text "Cannot coerce host var to type ...".
# Other errors of the same classes (a duplicate key is -670 and an IntegrityError, a
# missing table is also -494 but says nothing about coercion) and everything else (a lost
# connection, a permission error) prove nothing about the ENUM, so they propagate instead
# of being reported as a successful rejection.
SEMANTIC_ERRNO = -494


def is_invalid_enum_error(exc):
    return (
        isinstance(exc, pycubrid.ProgrammingError)
        and getattr(exc, "errno", None) == SEMANTIC_ERRNO
        and "coerce" in str(exc).lower()
    )


def reject_invalid(cursor, conn):
    print("\nInserting an out-of-set value ('urgent'):")
    try:
        cursor.execute(
            "INSERT INTO cookbook_tickets (id, title, priority) VALUES (?, ?, ?)",
            (99, "Bad value", "urgent"),
        )
    except pycubrid.Error as exc:
        conn.rollback()
        if not is_invalid_enum_error(exc):
            raise
        print(f"  rejected by ENUM constraint: {type(exc).__name__}")
        return
    # The insert went through: the lesson's claim is false, so do not keep the
    # row and do not let the script exit successfully.
    conn.rollback()
    raise RuntimeError(
        "ENUM accepted the out-of-set value 'urgent'; the rejection was not verified"
    )


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
