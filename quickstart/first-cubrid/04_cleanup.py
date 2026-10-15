"""04_cleanup.py — remove the tutorial's table, and only that table.

Step 5 of the beginner tutorial (quickstart/first-cubrid/README.md). Safe to
run any number of times: it drops cookbook_first_cubrid_notes only when the tutorial
created it, and leaves any other table alone.
"""

from __future__ import annotations

import sys

import pycubrid

# Local-only lab settings (see 01_first_query.py).
SETTINGS = {"host": "localhost", "port": 33000, "database": "testdb", "user": "dba", "password": ""}
TABLE = "cookbook_first_cubrid_notes"
MARKER = "created by the cubrid-cookbook first-cubrid tutorial"


def main() -> int:
    conn = pycubrid.connect(**SETTINGS)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT comment FROM db_class WHERE class_name = ?", (TABLE,))
        row = cursor.fetchone()
        if row is None:
            print(f"Nothing to clean up: {TABLE} does not exist.")
            return 0
        if row[0] != MARKER:
            print(f"{TABLE} was not created by this tutorial; it was left unchanged.")
            return 1
        cursor.execute("DROP TABLE cookbook_first_cubrid_notes")
        conn.commit()
        print(f"Dropped {TABLE}.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
