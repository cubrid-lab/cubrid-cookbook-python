"""01_async_pycubrid.py - Async CRUD with pycubrid.aio.

Demonstrates:
- Opening an async connection with ``pycubrid.aio.connect``
- Async context managers for connection and cursor
- Async execute / fetchone / fetchall / executemany
- Closing cleanly: leaving the ``async with`` blocks closes the cursor and the
  connection (``await conn.close()`` / ``await cur.close()`` do it by hand)

The ``pycubrid.aio`` submodule (stable since pycubrid 1.6) mirrors the
sync API but every I/O method is a coroutine. It uses asyncio under the
hood; there is no thread pool wrapping. Pair it with FastAPI, Starlette,
or any asyncio-native stack.

Run:
    python 01_async_pycubrid.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import pycubrid.aio  # type: ignore[import-not-found]
from pycubrid import DatabaseError  # type: ignore[import-not-found]

DB_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


async def setup_schema(conn: pycubrid.aio.AsyncConnection) -> None:
    cur = conn.cursor()
    await cur.execute("DROP TABLE IF EXISTS cookbook_async_demo")
    await cur.execute(
        """
        CREATE TABLE cookbook_async_demo (
            id    INT AUTO_INCREMENT PRIMARY KEY,
            name  VARCHAR(80) NOT NULL,
            score INT NOT NULL
        )
        """
    )
    await conn.commit()
    await cur.close()
    print("[setup] Created cookbook_async_demo")


async def cleanup(conn: pycubrid.aio.AsyncConnection) -> None:
    cur = conn.cursor()
    await cur.execute("DROP TABLE IF EXISTS cookbook_async_demo")
    await conn.commit()
    await cur.close()


async def main() -> None:
    print("=== pycubrid.aio Async CRUD Demo ===")
    print()

    # connect() is a coroutine that performs the TCP handshake + OPEN_DATABASE.
    # As an async context manager the connection commits on a clean exit, rolls
    # back on an exception, and closes either way.
    async with await pycubrid.aio.connect(**DB_CONFIG) as conn:
        try:
            await setup_schema(conn)

            # The cursor is an async context manager too: it is closed on exit.
            async with conn.cursor() as cur:
                # ----------------------------------------------------------
                # INSERT via executemany with a list of parameter tuples.
                # ----------------------------------------------------------
                rows = [
                    ("alice", 90),
                    ("bob", 75),
                    ("carol", 88),
                    ("dave", 60),
                ]
                await cur.executemany(
                    "INSERT INTO cookbook_async_demo (name, score) VALUES (?, ?)",
                    rows,
                )
                await conn.commit()
                print(f"[1] Inserted {len(rows)} rows asynchronously")

                # ----------------------------------------------------------
                # SELECT with fetchall().
                # ----------------------------------------------------------
                await cur.execute(
                    "SELECT id, name, score FROM cookbook_async_demo ORDER BY score DESC"
                )
                all_rows = await cur.fetchall()
                print()
                print("[2] All rows (fetchall):")
                for row in all_rows:
                    print(f"    id={row[0]}  name={row[1]}  score={row[2]}")

                # ----------------------------------------------------------
                # SELECT one row at a time with fetchone().
                # ----------------------------------------------------------
                await cur.execute("SELECT name, score FROM cookbook_async_demo ORDER BY id")
                print()
                print("[3] First row (fetchone):")
                first = await cur.fetchone()
                if first is not None:
                    print(f"    name={first[0]}  score={first[1]}")

                # ----------------------------------------------------------
                # UPDATE + commit.
                # ----------------------------------------------------------
                await cur.execute(
                    "UPDATE cookbook_async_demo SET score = ? WHERE name = ?",
                    (100, "alice"),
                )
                await conn.commit()
                print()
                print("[4] Updated alice's score to 100")
        finally:
            await cleanup(conn)

    print()
    print("--- async API summary ---")
    print("  await pycubrid.aio.connect(**DB_CONFIG)        -> AsyncConnection")
    print("  conn.cursor()                                   -> AsyncCursor (no await)")
    print("  await cur.execute(sql, params)                  -> AsyncCursor")
    print("  await cur.executemany(sql, params_list)         -> AsyncCursor")
    print("  await cur.fetchone() / fetchall() / fetchmany() -> rows")
    print("  await conn.commit() / conn.rollback()")
    print("  await conn.close()")
    print("  async with conn / conn.cursor()                 -> closed on exit")
    print()
    print("See also: 02_async_sqlalchemy.py for the SQLAlchemy async engine.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
