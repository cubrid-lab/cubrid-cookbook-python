"""01_isolation_levels.py - CUBRID isolation levels under MVCC.

Demonstrates:
- The isolation levels CUBRID accepts in raw SQL under MVCC
- Setting a level with raw SQL via pycubrid and reading it back
- A two-connection demonstration that dirty reads do NOT occur, even at the
  most permissive level, because CUBRID uses MVCC snapshots

CUBRID uses MVCC (Multi-Version Concurrency Control). In raw SQL the level is
set with a STRING name, not a numeric code:

    SET TRANSACTION ISOLATION LEVEL <name>

Only three levels are accepted under MVCC:
    READ COMMITTED    -> snapshot per statement   (GET code 4, CUBRID default)
    REPEATABLE READ   -> snapshot per transaction  (GET code 5)
    SERIALIZABLE      -> full serializable         (GET code 6)

READ UNCOMMITTED is intentionally rejected: MVCC readers never see another
transaction's uncommitted changes, so dirty reads are impossible at every
level. (Older CUBRID docs describe six numeric levels; those numeric codes are
no longer accepted by `SET TRANSACTION ISOLATION LEVEL` under MVCC.)

The current level is read back with:
    GET TRANSACTION ISOLATION LEVEL TO x  ; SELECT x
which returns the numeric GET code shown above.

Run:
    python 01_isolation_levels.py
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pycubrid  # type: ignore[import-not-found]
from pycubrid import DatabaseError  # type: ignore[import-not-found]

DB_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}

# The isolation levels CUBRID accepts under MVCC, in ascending strictness,
# with the numeric code returned by GET TRANSACTION ISOLATION LEVEL.
LEVELS: list[tuple[str, int]] = [
    ("READ COMMITTED", 4),
    ("REPEATABLE READ", 5),
    ("SERIALIZABLE", 6),
]


def get_connection() -> Any:
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_isolation_demo")
    cur.execute(
        """
        CREATE TABLE cookbook_isolation_demo (
            id    INT PRIMARY KEY,
            val   INT NOT NULL
        )
        """
    )
    cur.execute("INSERT INTO cookbook_isolation_demo (id, val) VALUES (?, ?)", (1, 100))
    conn.commit()
    cur.close()
    print("[setup] Created cookbook_isolation_demo with row (id=1, val=100)")


def cleanup(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_isolation_demo")
    conn.commit()
    cur.close()


def show_all_levels() -> None:
    """Open a fresh connection, set each accepted level, and read it back."""
    print()
    print("[1] Setting and reading each isolation level:")
    print()
    conn = get_connection()
    try:
        for name, expected_code in LEVELS:
            cur = conn.cursor()
            cur.execute(f"SET TRANSACTION ISOLATION LEVEL {name}")
            # CUBRID exposes the current level via the GET TRANSACTION statement,
            # which stores the numeric code into a bind name we then SELECT.
            cur.execute("GET TRANSACTION ISOLATION LEVEL TO x")
            cur.execute("SELECT x")
            row = cur.fetchone()
            current = row[0] if row else "?"
            match = "ok" if current == expected_code else f"expected {expected_code}"
            print(f"  SET ... {name:16s} ->  GET code={current} ({match})")
            cur.close()
    finally:
        conn.close()


def no_dirty_read_demo(level: str) -> None:
    """Show that uncommitted writes are NOT visible, even at *level*.

    Uses two connections on the same table:
      - writer: opens a transaction, UPDATEs the row, waits, ROLLBACKs
      - reader: opens a transaction at *level* and reads the row while the
        writer's UPDATE is still uncommitted.

    Under MVCC the reader sees the last committed value (100), never the
    uncommitted 999 -- so no dirty read is possible.
    """
    print()
    print(f"[2] Dirty-read demo at {level}:")
    print()

    writer_done = threading.Event()
    reader_done = threading.Event()
    observed: dict[str, Any] = {}

    def writer() -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
            cur.execute("UPDATE cookbook_isolation_demo SET val = 999 WHERE id = 1")
            # Hold the write uncommitted; do NOT commit yet.
            time.sleep(0.1)
            writer_done.set()
            # Wait for the reader to finish its observation, then discard.
            reader_done.wait(timeout=5.0)
            conn.rollback()
            cur.close()
        finally:
            conn.close()

    def reader() -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
            # Wait until the writer has an uncommitted UPDATE in flight.
            writer_done.wait(timeout=5.0)
            cur.execute("SELECT val FROM cookbook_isolation_demo WHERE id = 1")
            row = cur.fetchone()
            observed["val"] = row[0] if row else None
            reader_done.set()
            cur.close()
        finally:
            conn.close()

    t_writer = threading.Thread(target=writer, name="writer")
    t_reader = threading.Thread(target=reader, name="reader")
    t_writer.start()
    t_reader.start()
    t_writer.join(timeout=10.0)
    t_reader.join(timeout=10.0)

    val = observed.get("val")
    if val == 100:
        print("  reader observed val=100 (committed value) -> no dirty read (MVCC)")
    elif val == 999:
        print("  reader observed val=999 (UNCOMMITTED) -> dirty read OCCURRED")
    else:
        print(f"  reader observed val={val!r} (unexpected)")


def main() -> None:
    print("=== CUBRID Isolation Levels Demo ===")
    print()
    print("CUBRID uses MVCC. Three isolation levels are accepted in raw SQL:")
    print("  READ COMMITTED   - statement-level snapshot (default)")
    print("  REPEATABLE READ  - transaction-level snapshot")
    print("  SERIALIZABLE     - full serializable")
    print()

    conn = get_connection()
    try:
        setup_schema(conn)
    finally:
        conn.close()

    show_all_levels()

    # Under MVCC dirty reads are impossible even at the most permissive level.
    no_dirty_read_demo(level="READ COMMITTED")

    # Cleanup.
    conn = get_connection()
    try:
        cleanup(conn)
    finally:
        conn.close()

    print()
    print("--- Choosing an isolation level ---")
    print("  Read-heavy / typical web app : READ COMMITTED  (CUBRID default)")
    print("  Consistent multi-read units  : REPEATABLE READ")
    print("  Strict serialization         : SERIALIZABLE")
    print()
    print("Tip: SQLAlchemy exposes these names via")
    print("     sqlalchemy_cubrid/dialect.py:_ISOLATION_LEVEL_MAP.")


if __name__ == "__main__":
    try:
        main()
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
