"""03_fetch_and_errors.py — CUBRIDdb rows and errors → pycubrid rows and errors.

Fetching:
* CUBRIDdb picks the row shape with conn.cursor(dictCursor=True).
  pycubrid cursors always return tuples; build dicts from cursor.description.
* A CLOB/BLOB column comes back from an ordinary pycubrid cursor as a LOB
  handle (a dict), not as the text or bytes (see fundamentals/pycubrid/06_lob.py).

Errors:
* CUBRIDdb raises with args == (error_code, "ERROR: DBMS, <code>, <message>").
* pycubrid raises with args == (message,) and puts the CUBRID error number on
  DatabaseError.errno (also .code) and an SQLSTATE on .sqlstate.

CUBRIDdb (not executed here):
─────────────────────────────
    cur = conn.cursor(dictCursor=True)
    cur.execute("SELECT id, title FROM t")
    row = cur.fetchone()                    # {'id': 1, 'title': '...'}
    try:
        cur.execute("INSERT INTO t (id) VALUES (1)")
    except CUBRIDdb.IntegrityError as exc:
        code = exc.args[0]                  # e.g. -670

pycubrid (what this script runs):
─────────────────────────────────
    cur.execute("SELECT id, title FROM t")
    names = [column[0] for column in cur.description]
    row = dict(zip(names, cur.fetchone()))
    try:
        cur.execute("INSERT INTO t (id) VALUES (1)")
    except pycubrid.IntegrityError as exc:
        code = exc.errno                    # -670

The script uses its own table, cookbook_cdb_events, and stops without changing
anything if a table with that name exists that this recipe did not create.
"""

from __future__ import annotations

import sys

import pycubrid
from pycubrid.connection import Connection

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}
TABLE = "cookbook_cdb_events"
MARKER = "created by the cubrid-cookbook cubriddb-to-pycubrid recipes"


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
            cur.execute("DROP TABLE cookbook_cdb_events")
        cur.execute(
            "CREATE TABLE cookbook_cdb_events ("
            " id INT PRIMARY KEY,"
            " title VARCHAR(100) NOT NULL,"
            " body CLOB"
            ") COMMENT = 'created by the cubrid-cookbook cubriddb-to-pycubrid recipes'"
        )
        cur.executemany(
            "INSERT INTO cookbook_cdb_events (id, title, body) VALUES (?, ?, ?)",
            [(1, "deploy", "rolled out"), (2, "rollback", None), (3, "audit", "checked")],
        )
    conn.commit()
    return True


def fetch_shapes(conn: Connection) -> None:
    print("=== description and row shapes ===")
    with conn.cursor() as cur:
        cur.execute("SELECT id, title FROM cookbook_cdb_events ORDER BY id")
        print(f"  column names: {[column[0] for column in cur.description]}")
        print(f"  id is NUMBER: {cur.description[0][1] == pycubrid.NUMBER}, ", end="")
        print(f"title is STRING: {cur.description[1][1] == pycubrid.STRING}")
        names = [column[0] for column in cur.description]
        print(f"  fetchone():   {cur.fetchone()!r}")
        print(f"  as a dict:    {dict(zip(names, cur.fetchone()))!r}")
        print(f"  fetchmany(5): {cur.fetchmany(5)!r} (only the rows that are left)")
        print(f"  fetchall():   {cur.fetchall()!r} (result exhausted)")

        cur.execute("SELECT title FROM cookbook_cdb_events ORDER BY id")
        print(f"  iterating:    {[title for (title,) in cur]}")


def lob_column(conn: Connection) -> None:
    print("\n=== CLOB column ===")
    with conn.cursor() as cur:
        cur.execute("SELECT body FROM cookbook_cdb_events WHERE id = ?", (1,))
        handle = cur.fetchone()[0]
        print(
            f"  fetched as: {type(handle).__name__} with a 'lob_type' key: {'lob_type' in handle}"
        )
        cur.execute("SELECT body FROM cookbook_cdb_events WHERE id = ?", (2,))
        print(f"  a NULL CLOB is: {cur.fetchone()[0]!r}")
        # CAST in SQL when you only need short text and not the LOB API.
        cur.execute("SELECT CAST(body AS VARCHAR(100)) FROM cookbook_cdb_events WHERE id = ?", (1,))
        print(f"  CAST(body AS VARCHAR): {cur.fetchone()[0]!r}")


def database_errors(conn: Connection) -> None:
    print("\n=== Database errors: class, errno, sqlstate, args ===")
    with conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO cookbook_cdb_events (id, title) VALUES (?, ?)", (1, "duplicate")
            )
        except pycubrid.IntegrityError as exc:
            print(f"  duplicate key -> {type(exc).__name__}")
            print(f"    errno={exc.errno} code={exc.code} sqlstate={exc.sqlstate!r}")
            print(
                f"    len(args)={len(exc.args)}, args[0] is the message: {exc.args[0] == exc.msg}"
            )

        try:
            cur.execute("SELECT * FROM cookbook_cdb_no_such_table")
        except pycubrid.ProgrammingError as exc:
            print(f"  unknown table -> {type(exc).__name__}, errno={exc.errno}")

        try:
            cur.execute("SELEC 1")
        except pycubrid.DatabaseError as exc:
            print(f"  syntax error  -> {type(exc).__name__}, errno={exc.errno}")
    # A failed statement does not end the transaction; finish it explicitly.
    conn.rollback()


def interface_errors(conn: Connection) -> None:
    print("\n=== Interface errors: no database round trip ===")
    cur = conn.cursor()
    cur.close()
    try:
        cur.execute("SELECT 1")
    except pycubrid.InterfaceError as exc:
        print(f"  closed cursor -> InterfaceError ({exc}), has errno: {hasattr(exc, 'errno')}")
    is_database_error = issubclass(pycubrid.InterfaceError, pycubrid.DatabaseError)
    print(f"  InterfaceError is a DatabaseError: {is_database_error}")
    print(
        f"  InterfaceError is a pycubrid.Error: {issubclass(pycubrid.InterfaceError, pycubrid.Error)}"
    )


def main() -> int:
    conn = pycubrid.connect(**DB_CONFIG)
    created = False
    try:
        created = create_own_table(conn)
        if not created:
            return 1
        fetch_shapes(conn)
        lob_column(conn)
        database_errors(conn)
        interface_errors(conn)
    finally:
        if created:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DROP TABLE cookbook_cdb_events")
            conn.commit()
            print(f"\nDropped {TABLE}")
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
