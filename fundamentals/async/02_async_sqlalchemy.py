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

from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = "cubrid+aiopycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class CookbookAsyncOrmDemo(Base):
    __tablename__ = "cookbook_async_orm_demo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)


async def main() -> None:
    print("=== Async SQLAlchemy (cubrid+aiopycubrid) Demo ===")
    print()

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[1] Created table cookbook_async_orm_demo")

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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    print()
    print("[5] Dropped table and closed engine")

    print()
    print("--- async SQLAlchemy URL formats ---")
    print("  Sync:   cubrid+pycubrid://user:pass@host:port/db")
    print("  Async:  cubrid+aiopycubrid://user:pass@host:port/db")
    print()
    print("Requirements: pycubrid>=1.6, sqlalchemy-cubrid>=1.4.2, SQLAlchemy>=2.0")


if __name__ == "__main__":
    asyncio.run(main())
