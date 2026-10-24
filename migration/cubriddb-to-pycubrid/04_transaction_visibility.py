"""04_transaction_visibility.py — what other sessions see, before and after commit.

Code written for CUBRIDdb often has no commit() at all, because its
connections start with autocommit ON and every statement is committed when it
runs. Moved to pycubrid unchanged, the same code leaves its writes pending:
other sessions never see them, and closing the connection discards them.

CUBRIDdb (not executed here):
─────────────────────────────
    conn = CUBRIDdb.connect("CUBRID:localhost:33000:testdb:::", "dba", "")
    cur = conn.cursor()
    cur.execute("UPDATE t SET balance = balance - ? WHERE owner = ?", (50, "Alice"))
    # already committed, visible to everyone

pycubrid (what this script runs):
─────────────────────────────────
    conn = pycubrid.connect(host="localhost", port=33000, database="testdb",
                            user="dba", password="")
    try:
        cur.execute("UPDATE t SET balance = balance - ? WHERE owner = ?", (50, "Alice"))
        cur.execute("UPDATE t SET balance = balance + ? WHERE owner = ?", (50, "Bob"))
        conn.commit()       # both changes become visible together
    except Exception:
        conn.rollback()     # neither change is kept
        raise

The script uses its own table, cookbook_cdb_ledger, and stops without changing
anything if a table with that name exists that this recipe did not create.
"""

from __future__ import annotations

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
TABLE = "cookbook_cdb_ledger"
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
            cur.execute("DROP TABLE cookbook_cdb_ledger")
        cur.execute(
            "CREATE TABLE cookbook_cdb_ledger ("
            " id INT PRIMARY KEY,"
            " owner VARCHAR(50) NOT NULL,"
            " balance NUMERIC(12,2) NOT NULL"
            ") COMMENT = 'created by the cubrid-cookbook cubriddb-to-pycubrid recipes'"
        )
        cur.executemany(
            "INSERT INTO cookbook_cdb_ledger (id, owner, balance) VALUES (?, ?, ?)",
            [(1, "Alice", Decimal("100.00")), (2, "Bob", Decimal("20.00"))],
        )
    conn.commit()
    return True


def balances(conn: Connection) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT owner, balance FROM cookbook_cdb_ledger ORDER BY id")
        return ", ".join(f"{owner}={balance}" for owner, balance in cur.fetchall())


def commit_makes_visible(writer: Connection, observer: Connection) -> None:
    print("=== Commit: both updates appear together ===")
    with writer.cursor() as cur:
        cur.execute(
            "UPDATE cookbook_cdb_ledger SET balance = balance - ? WHERE owner = ?",
            (Decimal("50.00"), "Alice"),
        )
        cur.execute(
            "UPDATE cookbook_cdb_ledger SET balance = balance + ? WHERE owner = ?",
            (Decimal("50.00"), "Bob"),
        )
    print(f"  writer, before commit:   {balances(writer)}")
    print(f"  observer, before commit: {balances(observer)}")
    writer.commit()
    print(f"  observer, after commit:  {balances(observer)}")


def rollback_discards(writer: Connection, observer: Connection) -> None:
    print("\n=== Rollback: the pending change is discarded ===")
    with writer.cursor() as cur:
        cur.execute(
            "UPDATE cookbook_cdb_ledger SET balance = ? WHERE owner = ?", (Decimal("0.00"), "Bob")
        )
    print(f"  writer, before rollback: {balances(writer)}")
    writer.rollback()
    print(f"  writer, after rollback:  {balances(writer)}")
    print(f"  observer:                {balances(observer)}")


def failed_statement(writer: Connection, observer: Connection) -> None:
    print("\n=== A failed statement does not end the transaction ===")
    with writer.cursor() as cur:
        cur.execute(
            "INSERT INTO cookbook_cdb_ledger (id, owner, balance) VALUES (?, ?, ?)",
            (3, "Carol", Decimal("5.00")),
        )
        try:
            cur.execute(
                "INSERT INTO cookbook_cdb_ledger (id, owner, balance) VALUES (?, ?, ?)",
                (1, "Duplicate", Decimal("1.00")),
            )
        except pycubrid.IntegrityError as exc:
            print(f"  second INSERT failed: IntegrityError, errno={exc.errno}")
    print(f"  writer still holds the first INSERT: {balances(writer)}")
    print(f"  observer:                            {balances(observer)}")
    writer.rollback()
    print(f"  after rollback(), writer:            {balances(writer)}")


def autocommit_mode(writer: Connection, observer: Connection) -> None:
    print("\n=== autocommit ON: each statement commits on its own ===")
    writer.autocommit = True
    try:
        with writer.cursor() as cur:
            cur.execute(
                "INSERT INTO cookbook_cdb_ledger (id, owner, balance) VALUES (?, ?, ?)",
                (3, "Carol", Decimal("5.00")),
            )
            try:
                cur.execute(
                    "INSERT INTO cookbook_cdb_ledger (id, owner, balance) VALUES (?, ?, ?)",
                    (1, "Duplicate", Decimal("1.00")),
                )
            except pycubrid.IntegrityError as exc:
                print(f"  second INSERT failed: IntegrityError, errno={exc.errno}")
        writer.rollback()
        print(f"  observer after rollback(): {balances(observer)}")
        print("  -> the first INSERT was already committed; rollback() cannot undo it")
    finally:
        writer.autocommit = False


def main() -> int:
    writer = pycubrid.connect(**DB_CONFIG)
    # The observer reads in autocommit mode, so each read sees the latest
    # committed data and holds no lock that would block the DROP TABLE below.
    observer = pycubrid.connect(autocommit=True, **DB_CONFIG)
    created = False
    try:
        created = create_own_table(writer)
        if not created:
            return 1
        print(f"Start: {balances(observer)}\n")
        commit_makes_visible(writer, observer)
        rollback_discards(writer, observer)
        failed_statement(writer, observer)
        autocommit_mode(writer, observer)
    finally:
        observer.close()
        if created:
            writer.rollback()
            with writer.cursor() as cur:
                cur.execute("DROP TABLE cookbook_cdb_ledger")
            writer.commit()
            print(f"\nDropped {TABLE}")
        writer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
