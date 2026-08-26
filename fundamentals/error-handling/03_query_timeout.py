"""03_query_timeout.py - Bound a blocked operation with a client-side read_timeout.

Demonstrates:
- Why a server-side ``lock_timeout`` system parameter is not a reliable way to
  bound a client that is blocked waiting for a row lock on CUBRID 11.2
- The robust alternative: pass ``read_timeout`` to ``pycubrid.connect()`` so a
  blocked (or pathologically slow) operation fails fast with
  ``OperationalError`` instead of hanging the client forever
- Correct recovery: a connection whose socket timed out is no longer usable --
  discard it, and let a healthy connection release the lock and clean up

The scenario:
- ``writer_conn`` updates row id=1 inside an open transaction, holding its lock.
- ``blocked_conn`` (opened with ``read_timeout=2``) tries to update the same
  row. The server makes it wait for the lock; the client-side socket read
  timeout fires first and raises ``OperationalError``.

Run:
    python 03_query_timeout.py
"""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

READ_TIMEOUT_SECONDS = 2


class CursorProto(Protocol):
    def execute(self, sql: str, params: tuple[str, ...] | None = None) -> object: ...

    def close(self) -> None: ...


class ConnectionProto(Protocol):
    autocommit: bool

    def cursor(self) -> CursorProto: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class PycubridDriver(Protocol):
    OperationalError: type[Exception]

    def connect(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        read_timeout: int | None = None,
    ) -> ConnectionProto: ...


def pycubrid() -> PycubridDriver:
    module = import_module("pycubrid")
    return cast(PycubridDriver, cast(object, module))


def connect(driver: PycubridDriver, *, read_timeout: int | None = None) -> ConnectionProto:
    return driver.connect(
        host="localhost",
        port=33000,
        database="testdb",
        user="dba",
        password="",
        read_timeout=read_timeout,
    )


def _safe_close(closeable: CursorProto | ConnectionProto, driver: PycubridDriver) -> None:
    # A timed-out connection's socket is already dead, so close() itself can
    # raise. Swallow that so cleanup (and the final status line) still runs.
    try:
        closeable.close()
    except driver.OperationalError:
        pass


def main() -> None:
    print("=== Query Timeout Demo (client-side read_timeout) ===")
    print()

    driver = pycubrid()

    writer_conn = connect(driver)
    # The second connection fails fast instead of blocking indefinitely.
    blocked_conn = connect(driver, read_timeout=READ_TIMEOUT_SECONDS)

    writer = writer_conn.cursor()
    blocked = blocked_conn.cursor()

    try:
        _ = writer.execute("DROP TABLE IF EXISTS cookbook_timeout_demo")
        _ = writer.execute(
            """
            CREATE TABLE cookbook_timeout_demo (
                id INT PRIMARY KEY,
                note VARCHAR(100)
            )
            """
        )
        _ = writer.execute("INSERT INTO cookbook_timeout_demo (id, note) VALUES (1, 'initial')")
        writer_conn.commit()
        print("[setup] Created cookbook_timeout_demo and committed initial row")

        writer_conn.autocommit = False
        blocked_conn.autocommit = False

        # Writer takes and holds the row lock inside an open transaction.
        _ = writer.execute("UPDATE cookbook_timeout_demo SET note = 'locked' WHERE id = 1")
        print("[1] Writer holds an uncommitted lock on id=1")

        print(
            f"[2] Second connection (read_timeout={READ_TIMEOUT_SECONDS}s) attempts the same UPDATE..."
        )
        try:
            _ = blocked.execute("UPDATE cookbook_timeout_demo SET note = 'blocked' WHERE id = 1")
            blocked_conn.commit()
            print("[3] Unexpected: the UPDATE completed without timing out")
        except driver.OperationalError as error:
            # The socket read timed out while waiting for the server-held lock.
            print(f"[3] Timed out as expected: {type(error).__name__}: {error}")
            print("    -> a client-side read_timeout bounds an operation blocked on a lock")
            # The timed-out connection's socket is dead. Do NOT reuse it; just
            # close it in the finally block below.
    finally:
        # A healthy connection releases the lock and removes the demo table.
        try:
            writer_conn.rollback()
        except driver.OperationalError:
            pass
        try:
            _ = writer.execute("DROP TABLE IF EXISTS cookbook_timeout_demo")
            writer_conn.commit()
        except driver.OperationalError:
            pass
        _safe_close(writer, driver)
        _safe_close(blocked, driver)
        _safe_close(writer_conn, driver)
        _safe_close(blocked_conn, driver)
        print("[4] Writer released the lock and dropped the table; timed-out socket discarded")

    print()
    print("--- Key points ---")
    print("  pycubrid.connect(..., read_timeout=SECONDS) bounds blocked/slow operations")
    print("  Prefer a client-side read_timeout over relying on server lock_timeout")
    print("  A timed-out connection's socket is dead -- discard it, never reuse it")


if __name__ == "__main__":
    main()
