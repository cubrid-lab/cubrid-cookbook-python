"""07_collection_types.py - SET, MULTISET, and SEQUENCE columns on CUBRID.

Demonstrates:
- Defining CUBRID collection columns with sqlalchemy_cubrid.types
- Inserting collection values with CUBRID collection literals (``{...}``)
- Reading collection elements back with the ``TABLE(col)`` unnest join
- The semantic difference between the three collection kinds

CUBRID has three native collection types:

    SET        Unordered, NO duplicates.   e.g. unique tags on a post.
    MULTISET   Unordered, duplicates OK.   e.g. multiset of phone numbers.
    SEQUENCE   Ordered, duplicates OK.     e.g. ordered checklist steps.

Known driver limitation (why this recipe uses SQL, not ORM binding)
-------------------------------------------------------------------
As of the current ``pycubrid`` driver, collection columns cannot be round
-tripped through bound parameters:

  * INSERT: binding a Python ``set``/``list`` to a collection column raises
    ``ProgrammingError("unsupported parameter type")`` in
    ``pycubrid._cursor_common.format_parameter``.
  * SELECT: a collection column comes back as an opaque binary-encoded
    string, not a decoded Python list.

So this recipe still models the columns with ``sqlalchemy_cubrid.types`` (the
DDL is generated correctly), but writes values with CUBRID collection
literals and reads them back with the ``TABLE(collection)`` unnest join,
which returns one properly decoded element per row. If/when the driver gains
collection parameter binding, the insert/read paths can be simplified.

Run:
    python 07_collection_types.py
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy_cubrid.types import MULTISET, SEQUENCE, SET

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


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


def _literal(value: str) -> str:
    """Render a Python string as a single-quoted SQL literal (escapes quotes)."""
    return "'" + value.replace("'", "''") + "'"


def _collection_literal(values: list[str]) -> str:
    """Render a Python list as a CUBRID collection literal: ``{'a', 'b'}``."""
    return "{" + ", ".join(_literal(v) for v in values) + "}"


def _read_collection(conn: Connection, column: str, row_id: int) -> list[str]:
    """Read one collection column back as a Python list via ``TABLE()`` unnest.

    ``TABLE(col)`` expands a collection into one row per element, preserving
    SEQUENCE order and MULTISET duplicates. SET elements come back in CUBRID's
    normalized (sorted) order.
    """
    stmt = text(
        f"SELECT t.elem FROM cookbook_collection_demo, TABLE({column}) AS t(elem) WHERE id = :id"
    )
    return [r[0] for r in conn.execute(stmt, {"id": row_id})]


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
            "tags": ["python", "cubrid", "demo"],
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
        # INSERT: collection values via CUBRID collection literals.
        # (Bound set/list params are rejected by the driver; see module docstring.)
        # --------------------------------------------------------------
        for r in rows:
            conn.execute(
                text(
                    "INSERT INTO cookbook_collection_demo "
                    "(id, title, tags, phone_numbers, checklist) VALUES "
                    f"({r['id']}, {_literal(r['title'])}, "
                    f"{_collection_literal(r['tags'])}, "
                    f"{_collection_literal(r['phone_numbers'])}, "
                    f"{_collection_literal(r['checklist'])})"
                )
            )
    print()
    print(f"[2] Inserted {len(rows)} rows with collection columns")

    with engine.connect() as conn:
        # --------------------------------------------------------------
        # SELECT: read collections back with the TABLE() unnest join.
        # --------------------------------------------------------------
        print()
        print("[3] All rows:")
        ids = [
            r[0] for r in conn.execute(text("SELECT id FROM cookbook_collection_demo ORDER BY id"))
        ]
        for row_id in ids:
            title = conn.execute(
                text("SELECT title FROM cookbook_collection_demo WHERE id = :id"),
                {"id": row_id},
            ).scalar_one()
            print(f"    id={row_id}  title={title!r}")
            print(f"      tags          = {_read_collection(conn, 'tags', row_id)}")
            print(f"      phone_numbers = {_read_collection(conn, 'phone_numbers', row_id)}")
            print(f"      checklist     = {_read_collection(conn, 'checklist', row_id)}")

        # --------------------------------------------------------------
        # FILTER: ``value IN column`` membership on a SET column (server-side).
        # --------------------------------------------------------------
        print()
        print("[4] Rows whose tags include 'python' (server-side 'python' IN tags):")
        for row_id, title in conn.execute(
            text(
                "SELECT id, title FROM cookbook_collection_demo WHERE 'python' IN tags ORDER BY id"
            )
        ):
            tags = _read_collection(conn, "tags", row_id)
            print(f"    id={row_id}  title={title!r}  tags={tags}")

        # --------------------------------------------------------------
        # Demonstrate the SEMANTIC difference between the three kinds.
        # --------------------------------------------------------------
        print()
        print("[5] Semantic difference (observe duplicates/ordering):")
        print(f"    SET        tags          = {_read_collection(conn, 'tags', 1)}")
        print("                -> unique, CUBRID normalizes to sorted order")
        print(f"    MULTISET   phone_numbers = {_read_collection(conn, 'phone_numbers', 1)}")
        print("                -> duplicates PRESERVED (555-1000 appears twice)")
        print(f"    SEQUENCE   checklist     = {_read_collection(conn, 'checklist', 1)}")
        print("                -> order PRESERVED (open editor first, run tests last)")

    with engine.begin() as conn:
        # --------------------------------------------------------------
        # UPDATE: replace a collection column with a new literal value.
        # --------------------------------------------------------------
        new_checklist = ["benchmark", "optimize", "benchmark", "ship"]
        conn.execute(
            text(
                "UPDATE cookbook_collection_demo "
                f"SET checklist = {_collection_literal(new_checklist)} WHERE id = 3"
            )
        )
    with engine.connect() as conn:
        print()
        print(f"[6] Updated checklist for id=3: {_read_collection(conn, 'checklist', 3)}")
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
