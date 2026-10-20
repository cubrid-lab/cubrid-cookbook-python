"""01_engine.py — Engine creation and connection management.

Demonstrates:
- Creating engines with different URLs
- Connection pool settings
- Engine events
- Testing connectivity
"""

from __future__ import annotations

from sqlalchemy import create_engine, event, text

# Default connection URL — pycubrid driver (pure Python, no C build needed)
DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"

# Alternative: C-extension driver
# DATABASE_URL = "cubrid://dba:password@localhost:33000/testdb"


def basic_engine() -> None:
    """Create a basic engine and test connectivity."""
    print("=== Basic Engine ===")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 + 1"))
        print(f"  SELECT 1 + 1 = {result.scalar()}")

        result = conn.execute(text("SELECT version()"))
        print(f"  CUBRID version: {result.scalar()}")

    engine.dispose()
    print("  ✓ Engine created and disposed")


def engine_with_pool() -> None:
    """Engine with connection pool settings."""
    print("\n=== Engine with Pool Settings ===")

    engine = create_engine(
        DATABASE_URL,
        pool_size=5,  # Max connections in the pool
        max_overflow=10,  # Extra connections above pool_size
        pool_timeout=30,  # Seconds to wait for a connection
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True,  # Verify connections before use
        echo=False,  # Set True to log all SQL
    )

    # Pool status
    pool = engine.pool
    print(f"  Pool size: {pool.size()}")
    print(f"  Checked in: {pool.checkedin()}")
    print(f"  Checked out: {pool.checkedout()}")

    # Use a connection
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        print(f"  After connect — checked out: {pool.checkedout()}")

    print(f"  After close — checked out: {pool.checkedout()}")

    engine.dispose()
    print("  ✓ Pool engine created and disposed")


def engine_with_echo() -> None:
    """Engine with SQL logging enabled."""
    print("\n=== Engine with SQL Echo ===")

    engine = create_engine(DATABASE_URL)

    # The first connection runs the dialect's setup queries, which differ
    # between driver releases. Open it before turning echo on so that the log
    # shows only this example's statements. Passing echo=True to
    # create_engine() logs the setup queries as well.
    with engine.connect():
        pass
    engine.echo = True

    print("  (SQL statements will be logged below)")
    with engine.connect() as conn:
        conn.execute(text("SELECT 'hello from CUBRID'"))

    engine.dispose()
    print("  ✓ Echo mode demonstrated")


def engine_events() -> None:
    """Engine events — hooks for logging, metrics, etc."""
    print("\n=== Engine Events ===")

    engine = create_engine(DATABASE_URL)
    query_count = 0

    @event.listens_for(engine, "before_cursor_execute")
    def before_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        conn.execute(text("SELECT 2"))
        conn.execute(text("SELECT 3"))

    print(f"  Queries executed: {query_count}")

    engine.dispose()
    print("  ✓ Event listeners demonstrated")


def url_formats() -> None:
    """Show supported URL formats."""
    print("\n=== Supported URL Formats ===")

    urls = [
        ("pycubrid (pure Python)", "cubrid+pycubrid://dba@localhost:33000/testdb"),
        (
            "pycubrid with password",
            "cubrid+pycubrid://dba:password@localhost:33000/testdb",
        ),
        ("CUBRIDdb (C extension)", "cubrid://dba@localhost:33000/testdb"),
        ("CUBRIDdb with password", "cubrid://dba:password@localhost:33000/testdb"),
    ]

    for label, url in urls:
        print(f"  {label:30s}  {url}")

    # Test the current URL
    engine = create_engine(DATABASE_URL)
    print(f"\n  Active driver: {engine.dialect.driver}")
    print(f"  Dialect: {engine.dialect.name}")

    engine.dispose()


if __name__ == "__main__":
    basic_engine()
    engine_with_pool()
    engine_with_echo()
    engine_events()
    url_formats()
