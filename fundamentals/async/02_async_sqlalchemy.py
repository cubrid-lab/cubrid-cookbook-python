"""02_async_sqlalchemy.py - Async SQLAlchemy with the pycubrid async dialect.

Demonstrates:
- Building an ``AsyncEngine`` with the ``cubrid+aiopycubrid`` URL
- Async session via ``async_sessionmaker``
- ORM CRUD with ``await session.execute(select(...))`` and ``await session.commit()``
- Async schema creation / cleanup

The dialect is registered in sqlalchemy-cubrid as ``cubrid.aiopycubrid``.
Under the hood it uses ``pycubrid.aio`` (no thread-pool wrapping), so it
composes cleanly with FastAPI, Starlette, or any asyncio stack.

Run:
    python 02_async_sqlalchemy.py
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import Integer, String, inspect, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = "cubrid+aiopycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_async_orm_demo"


class Base(DeclarativeBase):
    pass


class CookbookAsyncOrmDemo(Base):
    __tablename__ = "cookbook_async_orm_demo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)


async def run_demo(engine: AsyncEngine) -> None:
    """Create the demo table, exercise async CRUD, then drop only what this run created."""
    async with engine.begin() as conn:
        # Refuse to touch a table this run did not create: ``create_all`` would silently
        # reuse it and ``drop_all`` would then delete someone else's data.
        if await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table(TABLE_NAME)):
            raise RuntimeError(
                f"Table {TABLE_NAME} already exists, so this demo will not modify or drop it. "
                "Drop it yourself or point DATABASE_URL at a disposable database, then re-run."
            )
        await conn.run_sync(Base.metadata.create_all)
    print("[1] Created table cookbook_async_orm_demo")

    failed = False
    try:
        await _crud_demo(engine)
    except BaseException:
        failed = True
        raise
    finally:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        except Exception as exc:  # noqa: BLE001 - never mask the error that got us here
            if not failed:
                raise
            print(f"warning: could not drop {TABLE_NAME}: {exc!r}", file=sys.stderr)


async def _crud_demo(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        # --------------------------------------------------------------
        # INSERT multiple rows in one flush.
        # --------------------------------------------------------------
        session.add_all(
            [
                CookbookAsyncOrmDemo(name="alice", score=90),
                CookbookAsyncOrmDemo(name="bob", score=75),
                CookbookAsyncOrmDemo(name="carol", score=88),
            ]
        )
        await session.commit()
        print("[2] Inserted 3 rows asynchronously")

        # --------------------------------------------------------------
        # SELECT with the 2.0-style ``select()`` API.
        # --------------------------------------------------------------
        result = await session.execute(
            select(CookbookAsyncOrmDemo).order_by(CookbookAsyncOrmDemo.score.desc())
        )
        rows = result.scalars().all()
        print()
        print("[3] Rows ordered by score DESC:")
        for row in rows:
            print(f"    id={row.id}  name={row.name}  score={row.score}")

        # --------------------------------------------------------------
        # UPDATE via scalar subquery pattern.
        # --------------------------------------------------------------
        bob = await session.scalar(
            select(CookbookAsyncOrmDemo).where(CookbookAsyncOrmDemo.name == "bob")
        )
        if bob is not None:
            bob.score = 95
            await session.commit()
            print()
            print(f"[4] Updated bob's score to {bob.score}")

        # --------------------------------------------------------------
        # DELETE all rows (cleanup before dropping the table).
        # --------------------------------------------------------------
        await session.execute(CookbookAsyncOrmDemo.__table__.delete())
        await session.commit()


async def main() -> None:
    print("=== Async SQLAlchemy (cubrid+aiopycubrid) Demo ===")
    print()

    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        await run_demo(engine)
    finally:
        # Release pooled connections even when setup, a query, a commit or cleanup failed.
        await engine.dispose()
    print()
    print("[5] Dropped table and closed engine")

    print()
    print("--- async SQLAlchemy URL formats ---")
    print("  Sync:   cubrid+pycubrid://user:pass@host:port/db")
    print("  Async:  cubrid+aiopycubrid://user:pass@host:port/db")
    print()
    print("Requirements: pycubrid>=1.6.1, sqlalchemy-cubrid>=1.5, SQLAlchemy[asyncio]>=2.0")


if __name__ == "__main__":
    asyncio.run(main())
