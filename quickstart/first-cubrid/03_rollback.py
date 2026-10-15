"""03_rollback.py — undo an uncommitted change with rollback.

Step 4 of the beginner tutorial (quickstart/first-cubrid/README.md). Run
02_save_and_verify.py first: this step uses its table and keeps its rows.
"""

from __future__ import annotations

import sys

import pycubrid

# Local-only lab settings (see 01_first_query.py).
SETTINGS = {"host": "localhost", "port": 33000, "database": "testdb", "user": "dba", "password": ""}
TABLE = "cookbook_first_cubrid_notes"
MARKER = "created by the cubrid-cookbook first-cubrid tutorial"


def count(conn: pycubrid.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cookbook_first_cubrid_notes")
    return cursor.fetchone()[0]


def main() -> int:
    conn = pycubrid.connect(**SETTINGS)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT comment FROM db_class WHERE class_name = ?", (TABLE,))
        row = cursor.fetchone()
        if row is None or row[0] != MARKER:
            print(f"The tutorial table {TABLE} is missing: run 02_save_and_verify.py first.")
            return 1

        print(f"Rows before the change: {count(conn)}")
        cursor.execute(
            "INSERT INTO cookbook_first_cubrid_notes (note) VALUES (?)",
            ("This row will be undone",),
        )
        print(f"Rows inside the open transaction: {count(conn)}")
        conn.rollback()  # discard everything since the last commit
        print(f"Rows after rollback: {count(conn)}")
        conn.commit()  # end the reading transaction too
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
