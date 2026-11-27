"""19_pagination.py - Server-side pagination idioms in CUBRID.

Demonstrates:
- Portable LIMIT ... OFFSET paging
- CUBRID-idiomatic FOR ORDERBY_NUM() BETWEEN ... AND ... paging
- Why the two return the SAME ordered page

Note on ROWNUM (not run here): CUBRID assigns ROWNUM before ORDER BY, so
``WHERE ROWNUM <= n ... ORDER BY`` sorts whichever n rows were read first rather
than returning the first n of the sorted result. Use ORDER BY with LIMIT or
FOR ORDERBY_NUM() for pages.

Rule of thumb: always ORDER BY a unique key before paging, otherwise the
"page" is undefined.
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

PAGE_SIZE = 3


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_catalog")
    cursor.execute(
        """
        CREATE TABLE cookbook_catalog (
            id   INT PRIMARY KEY,
            name VARCHAR(40) NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_catalog'")


def seed_catalog(cursor):
    rows = [(i, f"item-{i:02d}") for i in range(1, 11)]
    cursor.executemany("INSERT INTO cookbook_catalog (id, name) VALUES (?, ?)", rows)
    print(f"✓ Inserted catalog rows: {len(rows)}")


def _require_positive_page(page):
    # Pages are 1-based: page 0 or below would produce a negative LIMIT offset
    # or an invalid ORDERBY_NUM range, so reject it before any SQL is built.
    if page < 1:
        raise ValueError(f"page must be 1 or greater, got {page!r}")
    return page


def page_with_limit_offset(cursor, page):
    page = _require_positive_page(page)
    offset = (page - 1) * PAGE_SIZE
    cursor.execute(
        """
        SELECT id, name FROM cookbook_catalog
         ORDER BY id
         LIMIT ? OFFSET ?
        """,
        (PAGE_SIZE, offset),
    )
    return cursor.fetchall()


def page_with_orderby_num(cursor, page):
    page = _require_positive_page(page)
    lo = (page - 1) * PAGE_SIZE + 1
    hi = page * PAGE_SIZE
    # ORDERBY_NUM() is assigned AFTER the ORDER BY, so it pages an ordered set.
    cursor.execute(
        """
        SELECT id, name FROM cookbook_catalog
         ORDER BY id
           FOR ORDERBY_NUM() BETWEEN ? AND ?
        """,
        (lo, hi),
    )
    return cursor.fetchall()


def show_pages(cursor):
    for page in (1, 2, 3):
        lo = page_with_limit_offset(cursor, page)
        ob = page_with_orderby_num(cursor, page)
        match = "same" if lo == ob else "DIFFERENT"
        print(f"\nPage {page} (size {PAGE_SIZE}):")
        print(f"  LIMIT/OFFSET : {[r[1] for r in lo]}")
        print(f"  ORDERBY_NUM  : {[r[1] for r in ob]}")
        print(f"  -> both idioms agree: {match}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_catalog")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_catalog'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()
        seed_catalog(cursor)
        conn.commit()
        show_pages(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
