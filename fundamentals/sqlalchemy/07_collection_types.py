"""07_collection_types.py - SET, MULTISET, and SEQUENCE columns via SQLAlchemy ORM.

Demonstrates:
- Defining CUBRID collection columns with sqlalchemy_cubrid.types
- Inserting rows with collection literals
- Querying collection membership and size
- The semantic difference between the three collection kinds

CUBRID has three native collection types:

    SET        Unordered, NO duplicates.   e.g. unique tags on a post.
    MULTISET   Unordered, duplicates OK.  e.g. multiset of phone numbers.
    SEQUENCE   Ordered, duplicates OK.    e.g. ordered checklist steps.

All three are stored as a single column value and queryable with the
IN, ANY, and COUNT operators. The ``sqlalchemy_cubrid.types`` module
exposes them as SQLAlchemy types so ORM models can use them directly.

Run:
    python 07_collection_types.py
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from sqlalchemy_cubrid.types import MULTISET, SEQUENCE, SET

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class CookbookCollectionDemo(Base):
    """Table with one column of each CUBRID collection type."""

    __tablename__ = "cookbook_collection_demo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    tags: Mapped[Any] = mapped_column(SET(String(40)))  # unique, unordered
    phone_numbers: Mapped[Any] = mapped_column(MULTISET(String(20)))  # duplicates OK
    checklist: Mapped[Any] = mapped_column(SEQUENCE(String(200)))  # ordered


def main() -> None:
    print("=== CUBRID Collection Types (SET / MULTISET / SEQUENCE) ===")
    print()

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    print("[1] Created table cookbook_collection_demo")
    print("      tags         SET(40)         unique, unordered")
    print("      phone_numbers MULTISET(20)   duplicates allowed")
    print("      checklist     SEQUENCE(200)  ordered, duplicates allowed")

    with Session(engine) as session:
        # ------------------------------------------------------------------
        # INSERT: Python lists/tuples bind directly to collection columns.
        # ------------------------------------------------------------------
        rows = [
            CookbookCollectionDemo(
                title="First task",
                tags={"python", "cubrid", "demo"},
                phone_numbers=["555-1000", "555-1000", "555-2000"],
                checklist=["open editor", "write code", "run tests"],
            ),
            CookbookCollectionDemo(
                title="Second task",
                tags={"python", "orm"},
                phone_numbers=["555-3000"],
                checklist=["review PR", "merge"],
            ),
            CookbookCollectionDemo(
                title="Third task",
                tags={"rust", "systems"},
                phone_numbers=["555-4000", "555-4000"],
                checklist=["benchmark", "profile", "optimize", "benchmark"],
            ),
        ]
        session.add_all(rows)
        session.commit()
        print()
        print(f"[2] Inserted {len(rows)} rows with collection columns")

        # ------------------------------------------------------------------
        # SELECT: read collections back as Python lists/tuples.
        # ------------------------------------------------------------------
        print()
        print("[3] All rows:")
        stmt = select(CookbookCollectionDemo).order_by(CookbookCollectionDemo.id)
        for row in session.scalars(stmt):
            print(f"    id={row.id}  title={row.title!r}")
            print(f"      tags          = {row.tags}")
            print(f"      phone_numbers = {row.phone_numbers}")
            print(f"      checklist     = {row.checklist}")

        # ------------------------------------------------------------------
        # FILTER: ``IN`` predicate against a SET column.
        #
        # CUBRID supports ``'value' IN column`` and ``column = ALL('x')``
        # operators on collection columns. We rely on a Python-side filter
        # here for portability across SQLAlchemy versions.
        # ------------------------------------------------------------------
        print()
        print("[4] Rows whose tags include 'python' (client-side filter):")
        for row in session.scalars(
            select(CookbookCollectionDemo).order_by(CookbookCollectionDemo.id)
        ):
            tags = set(row.tags or [])
            if "python" in tags:
                print(f"    id={row.id}  title={row.title!r}  tags={row.tags}")

        # ------------------------------------------------------------------
        # Demonstrate the SEMANTIC difference between the three kinds.
        # ------------------------------------------------------------------
        print()
        print("[5] Semantic difference (observe duplicates/ordering):")
        first = session.scalars(
            select(CookbookCollectionDemo).where(CookbookCollectionDemo.id == 1)
        ).one()
        print(f"    SET        tags         = {first.tags!r}")
        print("                -> unique, no duplicates, no ordering guarantee")
        print(f"    MULTISET   phone_numbers= {first.phone_numbers!r}")
        print("                -> duplicates PRESERVED (555-1000 appears twice)")
        print(f"    SEQUENCE   checklist    = {first.checklist!r}")
        print("                -> order PRESERVED (open editor first, run tests last)")

        # ------------------------------------------------------------------
        # UPDATE: replace a collection column with a new list.
        # ------------------------------------------------------------------
        third = session.scalars(
            select(CookbookCollectionDemo).where(CookbookCollectionDemo.id == 3)
        ).one()
        third.checklist = ["benchmark", "optimize", "benchmark", "ship"]
        session.commit()
        print()
        print(f"[6] Updated checklist for id=3: {third.checklist!r}")
        print("    (SEQUENCE preserves the new order and the duplicate 'benchmark')")

        # ------------------------------------------------------------------
        # Cleanup.
        # ------------------------------------------------------------------
        session.execute(delete(CookbookCollectionDemo))
        session.commit()

    Base.metadata.drop_all(engine)
    engine.dispose()
    print()
    print("[7] Cleaned up table and closed engine")

    print()
    print("--- Choosing a collection type ---")
    print("  Need uniqueness?           -> SET")
    print("  Duplicates meaningful?     -> MULTISET (e.g. vote tallies)")
    print("  Insertion order matters?   -> SEQUENCE (e.g. ordered steps)")
    print()
    print("See: https://www.cubrid.org/manual/en/11.2/sql/datatype.html#collection-types")


if __name__ == "__main__":
    main()
