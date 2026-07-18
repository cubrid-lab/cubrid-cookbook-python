"""01_isolation_levels.py - CUBRID isolation levels and dirty-read demonstration.

Demonstrates:
- All 6 numeric isolation levels CUBRID supports (1 = most permissive, 6 = serializable)
- Setting levels with raw SQL via pycubrid
- Reading the current level back
- A two-connection dirty-read demonstration at level 1 vs level 4

CUBRID uses NUMERIC isolation levels in raw SQL:
    SET TRANSACTION ISOLATION LEVEL <1..6>

The mapping (per sqlalchemy-cubrid/_ISOLATION_LEVEL_MAP):
    1 = READ COMMITTED SCHEMA, READ UNCOMMITTED INSTANCES  (dirty reads possible)
    2 = READ COMMITTED SCHEMA, READ COMMITTED INSTANCES
    3 = REPEATABLE READ SCHEMA, READ UNCOMMITTED INSTANCES
    4 = REPEATABLE READ SCHEMA, READ COMMITTED INSTANCES   (CUBRID default)
    5 = REPEATABLE READ SCHEMA, REPEATABLE READ INSTANCES
    6 = SERIALIZABLE                                        (highest)

Each level combines a SCHEMA stability (DDL visibility) with an INSTANCES
stability (row-level visibility). The dual granularity is CUBRID-specific;
most databases expose only row-level isolation.

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

# Numeric level -> human-readable name (mirrors sqlalchemy-cubrid mapping).
LEVEL_NAMES: dict[int, str] = {
    1: "READ COMMITTED SCHEMA, READ UNCOMMITTED INSTANCES",
    2: "READ COMMITTED SCHEMA, READ COMMITTED INSTANCES",
    3: "REPEATABLE READ SCHEMA, READ UNCOMMITTED INSTANCES",
    4: "REPEATABLE READ SCHEMA, READ COMMITTED INSTANCES",
    5: "REPEATABLE READ SCHEMA, REPEATABLE READ INSTANCES",
    6: "SERIALIZABLE",
}


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
    """Open a fresh connection, set each of the 6 levels, and read it back."""
    print()
    print("[1] Setting and reading each isolation level:")
    print()
    conn = get_connection()
    try:
        for level in range(1, 7):
            cur = conn.cursor()
            cur.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
            # CUBRID exposes the current level via the GET TRANSACTION statement.
            cur.execute("GET TRANSACTION ISOLATION LEVEL TO x")
            cur.execute("SELECT x")
            row = cur.fetchone()
            current = row[0] if row else "?"
            name = LEVEL_NAMES.get(int(current) if isinstance(current, int) else level, "?")
            print(f"  SET TRANSACTION ISOLATION LEVEL {level}  ->  current={current} ({name})")
            cur.close()
    finally:
        conn.close()


def dirty_read_demo(level: int, label: str) -> None:
    """Demonstrate whether uncommitted writes are visible at *level*.

    Uses two connections on the same table:
      - writer: opens a transaction, UPDATEs the row, waits, ROLLBACKs
      - reader: opens a transaction at *level*, reads the row BEFORE the
        writer commits. A dirty read returns the uncommitted value.
    """
    print()
    print(f"[2] Dirty-read demo at level {level} ({label}):")
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
            # Small sleep ensures the CAS broker has the row locked before
            # the reader wakes up, eliminating a theoretical startup race.
            time.sleep(0.1)
            writer_done.set()
            # Wait for the reader to finish its observation.
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
    if val == 999:
        print("  reader observed val=999 (UNCOMMITTED) -> dirty read OCCURRED")
    elif val == 100:
        print("  reader observed val=100 (committed value) -> no dirty read")
    else:
        print(f"  reader observed val={val!r} (unexpected)")


def main() -> None:
    print("=== CUBRID Isolation Levels Demo ===")
    print()
    print("CUBRID supports 6 numeric isolation levels. Each combines:")
    print("  - SCHEMA stability:  are DDL changes from other transactions visible?")
    print("  - INSTANCES stability: are uncommitted row changes visible?")
    print()

    conn = get_connection()
    try:
        setup_schema(conn)
    finally:
        conn.close()

    show_all_levels()

    # The most dramatic demonstration: level 1 allows dirty reads.
    dirty_read_demo(level=1, label="READ UNCOMMITTED INSTANCES")

    # At level 4 (CUBRID default) dirty reads are NOT possible.
    dirty_read_demo(level=4, label="READ COMMITTED INSTANCES (default)")

    # Cleanup.
    conn = get_connection()
    try:
        cleanup(conn)
    finally:
        conn.close()

    print()
    print("--- Choosing an isolation level ---")
    print("  Read-heavy analytics          : level 1-2  (max throughput)")
    print("  Typical web app (default)     : level 4   (CUBRID default)")
    print("  Financial / consistency-critical: level 5-6 (repeatable read / serializable)")
    print()
    print("Tip: SQLAlchemy exposes human-readable names. See")
    print("     sqlalchemy_cubrid/dialect.py:_ISOLATION_LEVEL_MAP for the mapping.")


if __name__ == "__main__":
    try:
        main()
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
