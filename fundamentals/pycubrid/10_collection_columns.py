"""10_collection_columns.py - Native SET/MULTISET/LIST columns.

Demonstrates:
- Creating collection-typed columns
- Inserting collection literals
- Updating collection values
- Reading collection columns back

Collection literals use CUBRID syntax: SET{...}, MULTISET{...}, LIST{...}.
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
        VALUES (?, ?, SET{'blue','beta','api'}, MULTISET{1,1,2,3}, LIST{'draft','review','publish'})
        """,
        (1, "Doc Workflow"),
    )
    cursor.execute(
        """
        INSERT INTO cookbook_collections (id, name, tags, permissions, ordered_steps)
        VALUES (?, ?, SET{'ops','critical'}, MULTISET{7,8,8}, LIST{'detect','mitigate','report'})
        """,
        (2, "Incident Flow"),
    )
    print("✓ Inserted collection examples")


def update_collections(cursor):
    print("\nBefore update:")
    read_collections(cursor)

    cursor.execute(
        """
        UPDATE cookbook_collections
           SET tags = SET{'blue','beta','api','stable'},
               permissions = MULTISET{1,2,2,4},
               ordered_steps = LIST{'draft','review','approve','publish'}
         WHERE id = ?
        """,
        (1,),
    )
    print(f"\n✓ Updated row id=1 collections (rows affected: {cursor.rowcount})")


def read_collections(cursor):
    def as_int(value):
        if isinstance(value, (bytes, bytearray)):
            return int.from_bytes(value, byteorder="big", signed=False)
        if isinstance(value, str):
            return int.from_bytes(value.encode("latin1"), byteorder="big", signed=False)
        return int(value)

    cursor.execute(
        """
        SELECT
            id,
            name,
            'blue' IN tags,
            8 IN permissions,
            ordered_steps = LIST{'draft','review','publish'},
            ordered_steps = LIST{'draft','review','approve','publish'}
          FROM cookbook_collections
         ORDER BY id
        """
    )
    rows = cursor.fetchall()
    print(f"Collections ({len(rows)} rows):")
    for row in rows:
        has_blue = as_int(row[2])
        has_perm_8 = as_int(row[3])
        steps_v1 = as_int(row[4])
        steps_v2 = as_int(row[5])
        print(f"  id={row[0]} name={row[1]}")
        print(f"    contains_tag_blue={has_blue} contains_permission_8={has_perm_8}")
        print(f"    matches_steps_v1={steps_v1} matches_steps_v2={steps_v2}")


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
