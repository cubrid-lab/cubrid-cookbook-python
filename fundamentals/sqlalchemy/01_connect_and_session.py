"""01_connect_and_session.py - Engine creation and Session basics with CUBRID.

Demonstrates:
- SQLAlchemy URL format for CUBRID
- Engine creation with practical pool defaults
- Session context manager usage
- Basic connectivity checks and clean shutdown
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


def main() -> None:
    print("=== SQLAlchemy + CUBRID: Connect and Session ===")
    print(f"Connection URL: {DATABASE_URL}")

    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

    try:
        print("\n[1] Running SELECT 1 with raw connection")
        with engine.connect() as connection:
            value = cast(int, connection.execute(text("SELECT 1")).scalar_one())
            version = cast(str, connection.execute(text("SELECT version()")).scalar_one())
            database_name = cast(str, connection.execute(text("SELECT database()")).scalar_one())
            current_user = cast(str, connection.execute(text("SELECT user()")).scalar_one())

        print(f"SELECT 1 result: {value}")
        print(f"CUBRID version: {version}")
        print(f"Database: {database_name}")
        print(f"Connected user: {current_user}")

        print("\n[2] Running SELECT 1 using Session context manager")
        with Session(engine) as session:
            value = cast(int, session.execute(text("SELECT 1")).scalar_one())
            print(f"Session SELECT 1 result: {value}")

        print("\n[3] Pool status snapshot")
        print(f"Pool status: {engine.pool.status()}")

        print("\nDone. Engine and Session usage completed successfully.")
    finally:
        engine.dispose()
        print("Engine disposed. Clean shutdown complete.")


if __name__ == "__main__":
    main()
