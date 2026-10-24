"""02_parameterized_crud.py — CUBRIDdb ? parameters → pycubrid ? parameters.

Both drivers use the qmark paramstyle, so SQL text with ? markers moves over
unchanged. What changes is how the values travel:

* CUBRIDdb prepares the statement and binds each value through CCI
  (cursor.execute -> _cs.prepare + _cs.bind_param).
* An ordinary pycubrid cursor converts each value to an escaped SQL literal in
  the driver and sends the finished statement. The driver does the quoting, so
  a value can never change the statement, but do not build SQL yourself with
  f-strings or % formatting: only ? markers get this protection.

CUBRIDdb (not executed here):
─────────────────────────────
    cur.execute("INSERT INTO t (customer, amount) VALUES (?, ?)",
                ("Alice", Decimal("19.99")))      # committed: autocommit ON

pycubrid (what this script runs):
─────────────────────────────────
    cur.execute("INSERT INTO t (customer, amount) VALUES (?, ?)",
                ("Alice", Decimal("19.99")))
    conn.commit()                                  # autocommit is OFF

The script uses its own table, cookbook_cdb_orders, and stops without changing
anything if a table with that name exists that this recipe did not create.
"""

from __future__ import annotations

import datetime
import sys
from decimal import Decimal

import pycubrid
from pycubrid.connection import Connection

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}
TABLE = "cookbook_cdb_orders"
MARKER = "created by the cubrid-cookbook cubriddb-to-pycubrid recipes"

# Stored as plain text; the ? marker keeps it from becoming SQL.
HOSTILE = "O'Reilly'); DROP TABLE cookbook_cdb_orders; --"


def create_own_table(conn: Connection) -> bool:
    """Create the recipe table; refuse to touch a same-named table it does not own."""
    with conn.cursor() as cur:
        cur.execute("SELECT comment FROM db_class WHERE class_name = ?", (TABLE,))
        row = cur.fetchone()
        if row is not None and (row[0] or "") != MARKER:
            print(f"A table named {TABLE} already exists and was not created by this recipe.")
            print("Nothing was changed.")
            return False
        if row is not None:
            print(f"Dropping {TABLE} left over from an interrupted run.")
            cur.execute("DROP TABLE cookbook_cdb_orders")
        cur.execute(
            "CREATE TABLE cookbook_cdb_orders ("
            " id INT AUTO_INCREMENT PRIMARY KEY,"
            " customer VARCHAR(100) NOT NULL,"
            " amount NUMERIC(10,2),"
            " due_on DATE,"
            " receipt BIT VARYING(64),"
            " memo VARCHAR(200)"
            ") COMMENT = 'created by the cubrid-cookbook cubriddb-to-pycubrid recipes'"
        )
    conn.commit()
    return True


def show_rows(conn: Connection, title: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, customer, amount, due_on, receipt, memo FROM cookbook_cdb_orders ORDER BY id"
        )
        rows = cur.fetchall()
    print(f"  {title}: {len(rows)} rows")
    for row in rows:
        print(f"    {row!r}")


def create(conn: Connection) -> None:
    print("=== Create: Python values bound with ? ===")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cookbook_cdb_orders (customer, amount, due_on, receipt, memo)"
            " VALUES (?, ?, ?, ?, ?)",
            ("Alice", Decimal("19.99"), datetime.date(2026, 1, 15), b"\x01\xff", None),
        )
        # executemany() takes a sequence of parameter tuples, as in CUBRIDdb.
        cur.executemany(
            "INSERT INTO cookbook_cdb_orders (customer, amount, due_on, receipt, memo)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                ("Bob", Decimal("0.10"), datetime.date(2026, 2, 1), None, "rush"),
                (HOSTILE, Decimal("1234.50"), None, b"\x00", "quoted safely"),
            ],
        )
        print(f"  executemany() rowcount: {cur.rowcount}")
    conn.commit()
    show_rows(conn, "after commit")


def read_types(conn: Connection) -> None:
    print("\n=== Read: Python types that come back ===")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT customer, amount, due_on, receipt, memo FROM cookbook_cdb_orders WHERE id = ?",
            (1,),
        )
        names = [column[0] for column in cur.description]
        row = cur.fetchone()
    for name, val in zip(names, row):
        print(f"  {name:<8} {type(val).__name__:<8} {val!r}")


def null_parameters(conn: Connection) -> None:
    print("\n=== NULL: None binds as SQL NULL ===")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cookbook_cdb_orders WHERE memo = ?", (None,))
        print(
            f"  WHERE memo = ? with None -> COUNT(*) = {cur.fetchone()[0]} (NULL = NULL is never true)"
        )
        cur.execute("SELECT COUNT(*) FROM cookbook_cdb_orders WHERE memo IS NULL")
        print(f"  WHERE memo IS NULL       -> COUNT(*) = {cur.fetchone()[0]}")


def update_and_delete(conn: Connection) -> None:
    print("\n=== Update and delete with ? ===")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE cookbook_cdb_orders SET amount = amount + ?, memo = ? WHERE customer = ?",
            (Decimal("5.01"), "adjusted", "Bob"),
        )
        print(f"  UPDATE rowcount: {cur.rowcount}")
        cur.execute("DELETE FROM cookbook_cdb_orders WHERE customer = ?", (HOSTILE,))
        print(f"  DELETE rowcount: {cur.rowcount} (the hostile text matched as a plain value)")
        cur.execute("DELETE FROM cookbook_cdb_orders WHERE customer = ?", ("nobody",))
        print(f"  DELETE of a missing row, rowcount: {cur.rowcount}")
    conn.commit()
    show_rows(conn, "after commit")


def main() -> int:
    conn = pycubrid.connect(**DB_CONFIG)
    created = False
    try:
        created = create_own_table(conn)
        if not created:
            return 1
        create(conn)
        read_types(conn)
        null_parameters(conn)
        update_and_delete(conn)
    finally:
        if created:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DROP TABLE cookbook_cdb_orders")
            conn.commit()
            print(f"\nDropped {TABLE}")
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
