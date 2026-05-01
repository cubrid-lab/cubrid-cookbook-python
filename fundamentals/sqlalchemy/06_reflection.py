"""06_reflection.py - Runtime schema reflection with SQLAlchemy Inspector API.

Demonstrates:
- Creating sample tables at runtime
- Using inspect() to discover tables, columns, PK/FK, and indexes
- Printing reflected schema details clearly
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, inspect

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


def main() -> None:
    engine = create_engine(DATABASE_URL)
    metadata = MetaData()

    authors = Table(
        "cookbook_ref_authors",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("author_name", String(100), nullable=False),
    )

    books = Table(
        "cookbook_ref_books",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("author_id", Integer, ForeignKey("cookbook_ref_authors.id")),
        Column("title", String(120), nullable=False),
        Column("price_cents", Integer, nullable=False),
    )

    print("=== SQLAlchemy Reflection Demo ===")

    try:
        metadata.create_all(engine)
        print("[1] Created tables cookbook_ref_authors and cookbook_ref_books")

        with engine.begin() as connection:
            _ = connection.execute(
                authors.insert(), [{"author_name": "Kim"}, {"author_name": "Lee"}]
            )
            _ = connection.execute(
                books.insert(),
                [
                    {"author_id": 1, "title": "SQL Basics", "price_cents": 2500},
                    {"author_id": 1, "title": "ORM Practical", "price_cents": 3300},
                    {"author_id": 2, "title": "CUBRID Guide", "price_cents": 2900},
                ],
            )

        inspector = inspect(engine)

        print("\n[2] Table discovery")
        tables = sorted(
            name for name in inspector.get_table_names() if name.startswith("cookbook_ref_")
        )
        for table_name in tables:
            print(f"- {table_name}")

        for table_name in tables:
            print(f"\n[3] Columns for {table_name}")
            columns = inspector.get_columns(table_name)
            for column in columns:
                nullable = "YES" if column.get("nullable", True) else "NO"
                print(
                    f"column={column['name']}, type={column['type']}, nullable={nullable}, default={column.get('default')}"
                )

            pk = inspector.get_pk_constraint(table_name)
            print(f"Primary key: {pk.get('constrained_columns', [])}")

            indexes = inspector.get_indexes(table_name)
            if indexes:
                for idx in indexes:
                    print(
                        f"Index: {idx.get('name')} columns={idx.get('column_names')} unique={idx.get('unique')}"
                    )
            else:
                print("Index: none")

            fks = inspector.get_foreign_keys(table_name)
            if fks:
                for fk in fks:
                    print(
                        f"Foreign key: {fk.get('constrained_columns')} -> {fk.get('referred_table')}.{fk.get('referred_columns')}"
                    )
            else:
                print("Foreign key: none")

        print("\nReflection demo completed.")
    finally:
        metadata.drop_all(engine)
        engine.dispose()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
