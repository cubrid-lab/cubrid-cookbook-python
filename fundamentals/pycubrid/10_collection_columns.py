"""10_collection_columns.py - Native SET/MULTISET/LIST columns.

Demonstrates:
- Creating collection-typed columns
- Binding collection values with ``pycubrid.types.Set`` / ``Multiset`` / ``Sequence``
- Reading collection columns back as Python containers with ``decode_collections=True``
- Updating collection values and filtering with server-side predicates

Driver requirements (why this recipe needs ``pycubrid>=1.9``):
- ``decode_collections=True`` (``connect()`` option, since 1.2.0) makes SET come
  back as ``frozenset`` and MULTISET/SEQUENCE (``LIST``) as ``list``. Without it
  the driver returns raw wire ``bytes``.
- The typed parameters ``Set``, ``Multiset`` and ``Sequence`` (since 1.9.0) bind a
  collection through ``?`` placeholders; they are sent as ``SET{...}``,
  ``MULTISET{...}`` and ``SEQUENCE{...}`` literals. A plain Python ``list``,
  ``tuple`` or ``set`` is still rejected with ``ProgrammingError``.
- Decoded values are plain containers, not these types: wrap them again
  (for example ``Set(row[1])``) to bind them.

Inline literals such as ``SET{'a','b'}`` remain valid SQL; typed binding just
removes the need to build them by hand.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

import pycubrid
from pycubrid.types import Multiset, Sequence, Set


DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
    "decode_collections": True,
}


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_collections")
    cursor.execute(
        """
        CREATE TABLE cookbook_collections (
            id            INT PRIMARY KEY,
            name          VARCHAR(100) NOT NULL,
            tags          SET(VARCHAR(50)),
            permissions   MULTISET(INT),
            ordered_steps LIST(VARCHAR(100))
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_collections'")


def insert_examples(cursor):
    cursor.execute(
        """
        INSERT INTO cookbook_collections (id, name, tags, permissions, ordered_steps)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            1,
            "Doc Workflow",
            Set(["blue", "beta", "api", "beta"]),  # SET drops the duplicate 'beta'
            Multiset([1, 1, 2, 3]),  # MULTISET keeps duplicates
            Sequence(["draft", "review", "publish"]),  # SEQUENCE keeps order
        ),
    )
    cursor.execute(
        """
        INSERT INTO cookbook_collections (id, name, tags, permissions, ordered_steps)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            2,
            "Incident Flow",
            Set(["ops", "critical"]),
            Multiset([7, 8, 8]),
            Sequence(["detect", "mitigate", "report"]),
        ),
    )
    cursor.execute(
        """
        INSERT INTO cookbook_collections (id, name, tags, permissions, ordered_steps)
        VALUES (?, ?, ?, ?, ?)
        """,
        (3, "Empty Collections", Set([]), Multiset([]), Sequence([])),
    )
    print("✓ Inserted collection examples with typed parameters")


def update_collections(cursor):
    print("\nBefore update:")
    read_collections(cursor)

    cursor.execute(
        """
        UPDATE cookbook_collections
           SET tags = ?,
               permissions = ?,
               ordered_steps = ?
         WHERE id = ?
        """,
        (
            Set(["blue", "beta", "api", "stable"]),
            Multiset([1, 2, 2, 4]),
            Sequence(["draft", "review", "approve", "publish"]),
            1,
        ),
    )
    print(f"\n✓ Updated row id=1 collections (rows affected: {cursor.rowcount})")


def read_collections(cursor):
    # With decode_collections=True the columns arrive as Python containers:
    # SET -> frozenset (unordered, so sort for stable output),
    # MULTISET -> list (duplicates kept), LIST/SEQUENCE -> list (order kept).
    cursor.execute(
        "SELECT id, name, tags, permissions, ordered_steps FROM cookbook_collections ORDER BY id"
    )
    rows = cursor.fetchall()
    print(f"Collections ({len(rows)} rows):")
    for row in rows:
        tags, permissions, steps = row[2], row[3], row[4]
        print(f"  id={row[0]} name={row[1]}")
        print(f"    tags={sorted(tags)} ({type(tags).__name__})")
        print(f"    permissions={sorted(permissions)} ({type(permissions).__name__})")
        print(f"    ordered_steps={steps} ({type(steps).__name__})")

    # Server-side membership and subset predicates work in WHERE clauses; a typed
    # parameter can be bound on the right-hand side of SUBSETEQ.
    cursor.execute(
        "SELECT id FROM cookbook_collections WHERE 'blue' IN tags AND 8 NOT IN permissions"
    )
    print(f"  rows with tag 'blue' and no permission 8: {[r[0] for r in cursor.fetchall()]}")
    cursor.execute(
        "SELECT id FROM cookbook_collections WHERE tags SUBSETEQ ? ORDER BY id",
        (Set(["ops", "critical", "api"]),),
    )
    print(
        f"  rows whose tags are a subset of ops/critical/api: {[r[0] for r in cursor.fetchall()]}"
    )


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_collections")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_collections'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()
        insert_examples(cursor)
        conn.commit()
        print("\nAfter insert:")
        read_collections(cursor)
        update_collections(cursor)
        conn.commit()
        print("\nAfter update:")
        read_collections(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
