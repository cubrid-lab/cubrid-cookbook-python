"""08_hierarchy_connect_by.py - Tree traversal with CONNECT BY.

Demonstrates:
- Modeling a simple hierarchy with parent_id
- Traversing full tree using START WITH ... CONNECT BY
- Traversing a subtree from a selected node
"""

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
    cursor.execute("DROP TABLE IF EXISTS cookbook_org_tree")
    cursor.execute(
        """
        CREATE TABLE cookbook_org_tree (
            id        INT PRIMARY KEY,
            parent_id INT,
            name      VARCHAR(100) NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_org_tree'")


def seed_tree(cursor):
    rows = [
        (1, None, "CEO"),
        (2, 1, "Engineering"),
        (3, 1, "Sales"),
        (4, 2, "Platform Team"),
        (5, 2, "Application Team"),
        (6, 3, "Domestic Sales"),
        (7, 3, "International Sales"),
        (8, 5, "Backend Squad"),
        (9, 5, "Frontend Squad"),
    ]
    cursor.executemany("INSERT INTO cookbook_org_tree (id, parent_id, name) VALUES (?, ?, ?)", rows)
    print(f"✓ Inserted tree nodes: {len(rows)}")


def list_full_tree(cursor):
    cursor.execute(
        """
        SELECT LEVEL, id, parent_id, name
          FROM cookbook_org_tree
         START WITH parent_id IS NULL
         CONNECT BY PRIOR id = parent_id
         ORDER BY LEVEL, id
        """
    )
    rows = cursor.fetchall()
    print(f"\nFull tree ({len(rows)} rows):")
    for row in rows:
        level = row[0]
        indent = "  " * (level - 1)
        print(f"  {indent}- id={row[1]} parent={row[2]} name={row[3]}")


def list_subtree(cursor, node_id):
    cursor.execute(
        """
        SELECT LEVEL, id, parent_id, name
          FROM cookbook_org_tree
         START WITH id = ?
         CONNECT BY PRIOR id = parent_id
         ORDER BY LEVEL, id
        """,
        (node_id,),
    )
    rows = cursor.fetchall()
    print(f"\nSubtree from node {node_id} ({len(rows)} rows):")
    for row in rows:
        level = row[0]
        indent = "  " * (level - 1)
        print(f"  {indent}- id={row[1]} parent={row[2]} name={row[3]}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_org_tree")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_org_tree'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()
        seed_tree(cursor)
        conn.commit()
        list_full_tree(cursor)
        list_subtree(cursor, 2)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
