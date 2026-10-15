"""02_save_and_verify.py — save rows, commit them and read them back from a second connection.

Step 4 of the beginner tutorial (quickstart/first-cubrid/README.md). It creates
the tutorial's own table, cookbook_first_cubrid_notes, and stops without changing
anything if a table with that name already exists.
"""

from __future__ import annotations

import sys

import pycubrid

# Local-only lab settings (see 01_first_query.py).
SETTINGS = {"host": "localhost", "port": 33000, "database": "testdb", "user": "dba", "password": ""}
TABLE = "cookbook_first_cubrid_notes"
MARKER = "created by the cubrid-cookbook first-cubrid tutorial"


def table_comment(cursor: pycubrid.Cursor) -> str | None:
    """Return the table's comment, or None when the table does not exist."""
    cursor.execute("SELECT comment FROM db_class WHERE class_name = ?", (TABLE,))
    row = cursor.fetchone()
    return None if row is None else (row[0] or "")


def main() -> int:
    conn = pycubrid.connect(**SETTINGS)
    try:
        cursor = conn.cursor()
        comment = table_comment(cursor)
        if comment == MARKER:
            print(f"{TABLE} is left over from an earlier run.")
            print("Run 04_cleanup.py, then run this step again.")
            return 1
        if comment is not None:
            print(f"A table named {TABLE} already exists and was not created by this tutorial.")
            print("Nothing was changed.")
            return 1

        cursor.execute(
            "CREATE TABLE cookbook_first_cubrid_notes ("
            " id INT AUTO_INCREMENT PRIMARY KEY,"
            " note VARCHAR(100) NOT NULL"
            ") COMMENT = 'created by the cubrid-cookbook first-cubrid tutorial'"
        )
        # Values go in as parameters (?), never pasted into the SQL text.
        for note in ("My first row", "My second row"):
            cursor.execute("INSERT INTO cookbook_first_cubrid_notes (note) VALUES (?)", (note,))
        conn.commit()  # make the table and both rows durable and visible to others
        print(f"Created {TABLE} and saved 2 rows.")
    finally:
        conn.close()

    # A second, independent connection sees only committed data.
    other = pycubrid.connect(**SETTINGS)
    try:
        cursor = other.cursor()
        cursor.execute("SELECT id, note FROM cookbook_first_cubrid_notes ORDER BY id")
        print("A second connection reads:")
        for row_id, note in cursor.fetchall():
            print(f"  {row_id}: {note}")
    finally:
        other.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
