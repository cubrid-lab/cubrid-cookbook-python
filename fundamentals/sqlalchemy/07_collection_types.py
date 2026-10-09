"""07_collection_types.py - SET, MULTISET, and SEQUENCE columns on CUBRID.

Demonstrates:
- Defining CUBRID collection columns with sqlalchemy_cubrid.types
- Binding Python lists/sets to collection columns (INSERT and UPDATE)
- Reading collection columns back as ``frozenset``/``list`` via ``decode_collections``
- The semantic difference between the three collection kinds

CUBRID has three native collection types:

    SET        Unordered, NO duplicates.   e.g. unique tags on a post.
    MULTISET   Unordered, duplicates OK.   e.g. multiset of phone numbers.
    SEQUENCE   Ordered, duplicates OK.     e.g. ordered checklist steps.

Driver requirements (why this recipe needs ``pycubrid>=1.9``)
-------------------------------------------------------------
  * READ: ``?decode_collections=true`` on the engine URL is forwarded to
    ``pycubrid.connect(decode_collections=True)`` (pycubrid 1.2.0+), so SET
    columns come back as ``frozenset`` and MULTISET/SEQUENCE as ``list``.
    Without it the driver returns raw wire ``bytes``.
  * WRITE: ``sqlalchemy-cubrid>=1.9`` with ``pycubrid>=1.9`` wraps a Python
    ``list``/``tuple``/``set`` bound to a SET/MULTISET/SEQUENCE column in
    ``pycubrid.types.Set``/``Multiset``/``Sequence`` (typed parameters, new in
    pycubrid 1.9.0) and sends it as a ``SET{...}``/``MULTISET{...}``/
    ``SEQUENCE{...}`` literal. A SEQUENCE is ordered, so pass a ``list`` or
    ``tuple`` for it, never a ``set``. Older drivers reject collection
    parameters with ``ProgrammingError``.

Nothing is built by hand: values are bound as ordinary Python containers and
read back as ordinary Python containers.

Run:
    python 07_collection_types.py
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String, create_engine, insert, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy_cubrid.types import MULTISET, SEQUENCE, SET

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb?decode_collections=true"


class Base(DeclarativeBase):
    pass


class CookbookCollectionDemo(Base):
    """Table with one column of each CUBRID collection type."""

    __tablename__ = "cookbook_collection_demo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    tags: Mapped[Any] = mapped_column(SET(String(40)))  # unique, unordered
    phone_numbers: Mapped[Any] = mapped_column(MULTISET(String(20)))  # dups OK
    checklist: Mapped[Any] = mapped_column(SEQUENCE(String(200)))  # ordered


def main() -> None:
    print("=== CUBRID Collection Types (SET / MULTISET / SEQUENCE) ===")
    print()

    engine = create_engine(DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("[1] Created table cookbook_collection_demo")
    print("      tags          SET(40)        unique, unordered")
    print("      phone_numbers MULTISET(20)   duplicates allowed")
    print("      checklist     SEQUENCE(200)  ordered, duplicates allowed")

    rows = [
        {
            "id": 1,
            "title": "First task",
            "tags": ["python", "cubrid", "demo", "python"],
            "phone_numbers": ["555-1000", "555-1000", "555-2000"],
            "checklist": ["open editor", "write code", "run tests"],
        },
        {
            "id": 2,
            "title": "Second task",
            "tags": ["python", "orm"],
            "phone_numbers": ["555-3000"],
            "checklist": ["review PR", "merge"],
        },
        {
            "id": 3,
            "title": "Third task",
            "tags": ["rust", "systems"],
            "phone_numbers": ["555-4000", "555-4000"],
            "checklist": ["benchmark", "profile", "optimize", "benchmark"],
        },
    ]

    with engine.begin() as conn:
        # --------------------------------------------------------------
        # INSERT: bind plain Python containers. The dialect wraps each one
        # in the typed collection parameter that matches its column.
        # (A duplicated 'python' in a SET value is dropped by the server.)
        # --------------------------------------------------------------
        conn.execute(insert(CookbookCollectionDemo), rows)
    print()
    print(f"[2] Inserted {len(rows)} rows by binding Python lists to collection columns")

    with engine.connect() as conn:
        # --------------------------------------------------------------
        # SELECT: collections arrive decoded (decode_collections=true).
        # SET is a frozenset (unordered), so sort it for stable output.
        # --------------------------------------------------------------
        print()
        print("[3] All rows:")
        for row in conn.execute(select(CookbookCollectionDemo).order_by(CookbookCollectionDemo.id)):
            print(f"    id={row.id}  title={row.title!r}")
            print(f"      tags          = {sorted(row.tags)}  ({type(row.tags).__name__})")
            print(
                f"      phone_numbers = {row.phone_numbers}  ({type(row.phone_numbers).__name__})"
            )
            print(f"      checklist     = {row.checklist}  ({type(row.checklist).__name__})")

        # --------------------------------------------------------------
        # FILTER: ``value IN column`` membership on a SET column (server-side).
        # --------------------------------------------------------------
        print()
        print("[4] Rows whose tags include 'python' (server-side 'python' IN tags):")
        for row_id, title, tags in conn.execute(
            text(
                "SELECT id, title, tags FROM cookbook_collection_demo "
                "WHERE 'python' IN tags ORDER BY id"
            )
        ):
            print(f"    id={row_id}  title={title!r}  tags={sorted(tags)}")

        # --------------------------------------------------------------
        # Demonstrate the SEMANTIC difference between the three kinds.
        # --------------------------------------------------------------
        first = conn.execute(
            select(CookbookCollectionDemo).where(CookbookCollectionDemo.id == 1)
        ).one()
        print()
        print("[5] Semantic difference (observe duplicates/ordering):")
        print(f"    SET        tags          = {sorted(first.tags)}")
        print("                -> unique (the duplicate input 'python' was dropped)")
        print(f"    MULTISET   phone_numbers = {sorted(first.phone_numbers)}")
        print("                -> duplicates PRESERVED (555-1000 appears twice)")
        print(f"    SEQUENCE   checklist     = {first.checklist}")
        print("                -> order PRESERVED (open editor first, run tests last)")

    with engine.begin() as conn:
        # --------------------------------------------------------------
        # UPDATE: replace a collection column with a new bound list.
        # --------------------------------------------------------------
        new_checklist = ["benchmark", "optimize", "benchmark", "ship"]
        conn.execute(
            update(CookbookCollectionDemo)
            .where(CookbookCollectionDemo.id == 3)
            .values(checklist=new_checklist)
        )
    with engine.connect() as conn:
        updated = conn.execute(
            select(CookbookCollectionDemo.checklist).where(CookbookCollectionDemo.id == 3)
        ).scalar_one()
        print()
        print(f"[6] Updated checklist for id=3: {updated}")
        print("    (SEQUENCE preserves the new order and the duplicate 'benchmark')")

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
