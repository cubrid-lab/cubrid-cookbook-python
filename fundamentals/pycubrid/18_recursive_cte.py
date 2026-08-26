"""18_recursive_cte.py - Recursive common table expressions (WITH RECURSIVE).

Demonstrates:
- A generated number series with an anchor + recursive member
- Walking a parent/child hierarchy and building a materialized path
- How WITH RECURSIVE contrasts with START WITH ... CONNECT BY (see 08)

CUBRID supports BOTH the ANSI recursive CTE shown here and Oracle-style
CONNECT BY. Recursive CTEs are portable across engines; CONNECT BY is terser
for pure tree walks.
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


def number_series(cursor):
    # Anchor (SELECT 1) + recursive member (n + 1) bounded by n < 5.
    cursor.execute(
        """
        WITH RECURSIVE nums (n) AS (
            SELECT 1
            UNION ALL
            SELECT n + 1 FROM nums WHERE n < 5
        )
        SELECT n FROM nums ORDER BY n
        """
    )
    values = [row[0] for row in cursor.fetchall()]
    print(f"\nGenerated number series: {values}")


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_employees")
    cursor.execute(
        """
        CREATE TABLE cookbook_employees (
            id       INT PRIMARY KEY,
            name     VARCHAR(50) NOT NULL,
            mgr_id   INT
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_employees'")


def seed_employees(cursor):
    rows = [
        (1, "Alice", None),
        (2, "Bob", 1),
        (3, "Carol", 1),
        (4, "Dave", 2),
        (5, "Eve", 2),
        (6, "Frank", 3),
    ]
    cursor.executemany(
        "INSERT INTO cookbook_employees (id, name, mgr_id) VALUES (?, ?, ?)",
        rows,
    )
    print(f"✓ Inserted employees: {len(rows)}")


def walk_hierarchy(cursor):
    # The recursive member joins each employee to its manager's accumulated path.
    cursor.execute(
        """
        WITH RECURSIVE org (id, name, mgr_id, lvl, path) AS (
            SELECT id, name, mgr_id, 1, CAST(name AS VARCHAR(200))
              FROM cookbook_employees
             WHERE mgr_id IS NULL
            UNION ALL
            SELECT e.id, e.name, e.mgr_id, o.lvl + 1, o.path || ' > ' || e.name
              FROM cookbook_employees e
              JOIN org o ON e.mgr_id = o.id
        )
        SELECT lvl, id, name, path FROM org ORDER BY path
        """
    )
    print("\nOrg hierarchy (ordered by path):")
    for lvl, emp_id, name, path in cursor.fetchall():
        indent = "  " * (lvl - 1)
        print(f"  {indent}- id={emp_id} depth={lvl} path={path}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_employees")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_employees'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        cursor = conn.cursor()
        number_series(cursor)
        cursor.close()

        setup_schema(conn)
        cursor = conn.cursor()
        seed_employees(cursor)
        conn.commit()
        walk_hierarchy(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
