"""16_batch_error_handling.py - Partial-failure handling for executemany_batch.

Demonstrates:
- Building a batch of heterogeneous SQL statements
- Intentionally injecting a failing statement mid-batch
- Catching the raised exception and inspecting the error code
- Retrying only the statements that did not run

Prior to pycubrid 1.6.1 (issue #186), ``executemany_batch`` silently
swallowed per-statement errors returned by the CAS broker in
``packet.errors``. The driver now raises the first failure using the
PEP 249 exception hierarchy, so callers can catch ``IntegrityError``,
``OperationalError``, etc. and implement retry / compensation logic.

Run:
    python 16_batch_error_handling.py
"""

from __future__ import annotations

from typing import Any

import pycubrid  # type: ignore[import-not-found]
from pycubrid import (  # type: ignore[import-not-found]
    DatabaseError,
    IntegrityError,
)

DB_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection() -> Any:
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_batch_probe")
    cur.execute(
        """
        CREATE TABLE cookbook_batch_probe (
            id    INT PRIMARY KEY,
            name  VARCHAR(80) NOT NULL
        )
        """
    )
    conn.commit()
    cur.close()
    print("[setup] Created cookbook_batch_probe (id PRIMARY KEY, name NOT NULL)")


def cleanup(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_batch_probe")
    conn.commit()
    cur.close()


def main() -> None:
    print("=== Batch Error Handling Demo (pycubrid 1.6.1+, issue #186 fix) ===")
    print()

    conn = get_connection()
    try:
        setup_schema(conn)

        # ------------------------------------------------------------------
        # Step 1: seed one row so a later INSERT duplicates its primary key.
        # ------------------------------------------------------------------
        cur = conn.cursor()
        cur.execute("INSERT INTO cookbook_batch_probe (id, name) VALUES (?, ?)", (1, "seed"))
        conn.commit()
        print("[1] Seeded row id=1 (will conflict later)")

        # ------------------------------------------------------------------
        # Step 2: build a batch where statement #3 duplicates id=1.
        #
        # executemany_batch accepts a LIST OF COMPLETE SQL STRINGS (not
        # parameterized placeholders). The driver sends them as a single
        # CAS batch-execute packet. The broker returns per-statement results
        # AND per-statement errors. The driver raises the first error.
        # ------------------------------------------------------------------
        sql_list = [
            "INSERT INTO cookbook_batch_probe (id, name) VALUES (2, 'alpha')",
            "INSERT INTO cookbook_batch_probe (id, name) VALUES (3, 'beta')",
            "INSERT INTO cookbook_batch_probe (id, name) VALUES (1, 'DUPLICATE')",  # fails
            "INSERT INTO cookbook_batch_probe (id, name) VALUES (4, 'gamma')",
            "INSERT INTO cookbook_batch_probe (id, name) VALUES (5, 'delta')",
        ]

        print(f"[2] Submitting batch of {len(sql_list)} statements (stmt #3 duplicates id=1)")

        try:
            cur.executemany_batch(sql_list, auto_commit=False)
        except IntegrityError as exc:
            # The CAS error code is exposed on the exception (exc.args[0]
            # is typically the numeric code; exc.args[1] is the message).
            print(f"[3] Caught IntegrityError as expected: {exc}")
            print(f"    args={exc.args!r}")
        except DatabaseError as exc:
            # Some CUBRID versions classify PRIMARY KEY violations as a
            # generic DatabaseError rather than IntegrityError. Either way,
            # the batch stopped at the first failing statement.
            print(f"[3] Caught DatabaseError: {exc}")
            print(f"    args={exc.args!r}")

        # ------------------------------------------------------------------
        # Step 3: inspect which statements actually committed.
        #
        # IMPORTANT: CUBRID's batch-execute runs each statement in its own
        # implicit transaction unless auto_commit=False is set AND the caller
        # explicitly commits. Statements BEFORE the failure may or may not
        # be visible depending on broker configuration; statements AFTER the
        # failure are NOT executed.
        # ------------------------------------------------------------------
        cur.execute("SELECT id, name FROM cookbook_batch_probe ORDER BY id")
        visible = cur.fetchall()
        print(f"[4] Rows visible after failure: {len(visible)}")
        for row in visible:
            print(f"    id={row[0]}  name={row[1]}")

        # ------------------------------------------------------------------
        # Step 4: demonstrate retry of the un-executed tail.
        #
        # In production, you typically split the batch on failure and retry
        # the statements that come AFTER the failing one. Here we retry
        # statements #4 and #5 (indices 3 and 4).
        # ------------------------------------------------------------------
        print()
        print("[5] Retrying statements after the failing one...")
        retry_list = sql_list[3:]  # gamma + delta
        cur.executemany_batch(retry_list, auto_commit=False)
        conn.commit()
        print(f"    Retried {len(retry_list)} statements successfully")

        cur.execute("SELECT id, name FROM cookbook_batch_probe ORDER BY id")
        final_rows = cur.fetchall()
        print(f"[6] Final row count: {len(final_rows)}")
        for row in final_rows:
            print(f"    id={row[0]}  name={row[1]}")

        cur.close()
    finally:
        try:
            cleanup(conn)
        finally:
            conn.close()

    print()
    print("--- API summary ---")
    print("  cursor.executemany_batch(sql_list, auto_commit=None)")
    print("    sql_list:    list[str] of COMPLETE SQL statements")
    print("    auto_commit: True = each stmt auto-commits; False = caller commits")
    print("  Returns: list[tuple[int, int]] of (result_code, affected_count)")
    print("  Raises:  PEP 249 exception on first per-statement failure")
    print()
    print("See also: pycubrid issue #186 for the silent-swallow bug this fixes.")


if __name__ == "__main__":
    main()
