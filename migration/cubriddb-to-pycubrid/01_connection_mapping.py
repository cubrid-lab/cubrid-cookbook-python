"""01_connection_mapping.py — CUBRIDdb connect() → pycubrid connect().

The official CUBRIDdb driver takes one CCI URL plus user and password, and the
connection it returns starts with autocommit ON. pycubrid takes keyword
arguments and starts with autocommit OFF.

CUBRIDdb (what you are replacing; not executed here):
─────────────────────────────────────────────────────
    import CUBRIDdb

    conn = CUBRIDdb.connect("CUBRID:localhost:33000:testdb:::", "dba", "")
    cur = conn.cursor()
    cur.execute("INSERT INTO ...")      # committed at once: autocommit is ON
    cur.close()
    conn.close()

pycubrid (what this script runs):
─────────────────────────────────
    import pycubrid

    conn = pycubrid.connect(host="localhost", port=33000, database="testdb",
                            user="dba", password="")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ...")  # pending until conn.commit()
    conn.commit()
    conn.close()

The script uses its own table, cookbook_cdb_connect, and stops without changing
anything if a table with that name exists that this recipe did not create.
"""

from __future__ import annotations

import sys

import pycubrid
from pycubrid.connection import Connection

# CUBRIDdb DSN "CUBRID:localhost:33000:testdb:::" → keyword arguments.
DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}
TABLE = "cookbook_cdb_connect"
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
            cur.execute("DROP TABLE cookbook_cdb_connect")
        cur.execute(
            "CREATE TABLE cookbook_cdb_connect ("
            " id INT AUTO_INCREMENT PRIMARY KEY,"
            " label VARCHAR(50) NOT NULL"
            ") COMMENT = 'created by the cubrid-cookbook cubriddb-to-pycubrid recipes'"
        )
    conn.commit()  # DDL is transactional while autocommit is off: commit it
    return True


def row_count(conn: Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cookbook_cdb_connect")
        return cur.fetchone()[0]


def module_contract() -> None:
    print("=== PEP 249 module globals ===")
    print(f"  apilevel     = {pycubrid.apilevel!r}")
    print(f"  paramstyle   = {pycubrid.paramstyle!r}  (? markers, same as CUBRIDdb)")
    print(
        f"  threadsafety = {pycubrid.threadsafety}  (threads may share the module, not a connection)"
    )


def autocommit_off(conn: Connection, observer: Connection) -> None:
    print("\n=== Default: autocommit OFF ===")
    print(f"  conn.autocommit after connect: {conn.autocommit}")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO cookbook_cdb_connect (label) VALUES (?)", ("never committed",))
    print("  inserted 1 row, no commit()")
    print(f"  same session COUNT(*):      {row_count(conn)}  (its own pending row)")
    print(f"  second connection COUNT(*): {row_count(observer)}")
    conn.rollback()
    print(f"  after rollback(), second connection COUNT(*): {row_count(observer)}")


def autocommit_on(conn: Connection, observer: Connection) -> None:
    print("\n=== Opt in: autocommit ON (the CUBRIDdb connect-time mode) ===")
    conn.autocommit = True
    print(f"  conn.autocommit = {conn.autocommit}")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO cookbook_cdb_connect (label) VALUES (?)", ("autocommitted",))
    print("  inserted 1 row, no commit()")
    print(f"  second connection COUNT(*): {row_count(observer)}")
    conn.autocommit = False
    print(f"  back to conn.autocommit = {conn.autocommit}")


def closed_objects(conn: Connection) -> None:
    print("\n=== Cursor and connection closing ===")
    with conn.cursor() as cur:
        cur.execute("SELECT label FROM cookbook_cdb_connect ORDER BY id")
        print(f"  inside 'with conn.cursor()': {cur.fetchall()}")
    try:
        cur.execute("SELECT 1")
    except pycubrid.InterfaceError as exc:
        print(f"  cursor after the with block: InterfaceError ({exc})")


def main() -> int:
    conn = pycubrid.connect(**DB_CONFIG)
    # The observer reads in autocommit mode, so it never holds a lock that
    # would block the DROP TABLE below.
    observer = pycubrid.connect(autocommit=True, **DB_CONFIG)
    created = False
    try:
        module_contract()
        created = create_own_table(conn)
        if not created:
            return 1
        autocommit_off(conn, observer)
        autocommit_on(conn, observer)
        closed_objects(conn)
    finally:
        observer.close()
        if created:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DROP TABLE cookbook_cdb_connect")
            conn.commit()
            print(f"\nDropped {TABLE}")
        conn.close()
    try:
        conn.cursor()
    except pycubrid.InterfaceError as exc:
        print(f"conn.cursor() after conn.close(): InterfaceError ({exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
