"""06_reflection.py — Schema reflection with CUBRID.

Demonstrates:
- Inspecting existing tables
- Reflecting table structure (columns, types, constraints)
- Reflecting indexes and foreign keys
- Auto-loading tables from the database
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Double,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    text,
)

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


def setup(engine) -> None:
    """Create some tables for reflection."""
    print("=== Reflection — Setup ===")

    metadata = MetaData()

    Table(
        "cookbook_reflect_authors",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(100), nullable=False),
        Column("country", String(50)),
    )

    Table(
        "cookbook_reflect_articles",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("title", String(200), nullable=False),
        Column("author_id", Integer, ForeignKey("cookbook_reflect_authors.id")),
        Column("views", Integer, default=0),
        Column("rating", Double, default=0.0),
    )

    metadata.drop_all(engine)
    metadata.create_all(engine)

    # Add an index
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_articles_views ON cookbook_reflect_articles (views)"))

    print("  ✓ Created tables with FK and index")


def list_tables(engine) -> None:
    """List all tables in the database."""
    print("\n=== List Tables ===")
    insp = inspect(engine)
    tables = insp.get_table_names()

    cookbook_tables = [t for t in tables if t.startswith("cookbook_reflect_")]
    print(f"  Cookbook tables ({len(cookbook_tables)}):")
    for t in sorted(cookbook_tables):
        print(f"    • {t}")


def reflect_columns(engine) -> None:
    """Inspect column details."""
    print("\n=== Reflect Columns ===")
    insp = inspect(engine)

    for table_name in ["cookbook_reflect_authors", "cookbook_reflect_articles"]:
        columns = insp.get_columns(table_name)
        print(f"\n  {table_name}:")
        print(f"    {'Column':15s}  {'Type':20s}  {'Nullable':>8s}  {'Default':>10s}")
        print(f"    {'------':15s}  {'----':20s}  {'--------':>8s}  {'-------':>10s}")
        for col in columns:
            nullable = "Yes" if col.get("nullable", True) else "No"
            default = str(col.get("default", "")) or ""
            col_type = str(col["type"])
            print(f"    {col['name']:15s}  {col_type:20s}  {nullable:>8s}  {default:>10s}")


def reflect_constraints(engine) -> None:
    """Inspect primary keys, foreign keys, and unique constraints."""
    print("\n=== Reflect Constraints ===")
    insp = inspect(engine)

    # Primary keys
    for table_name in ["cookbook_reflect_authors", "cookbook_reflect_articles"]:
        pk = insp.get_pk_constraint(table_name)
        print(f"  {table_name} PK: {pk['constrained_columns']}")

    # Foreign keys
    fks = insp.get_foreign_keys("cookbook_reflect_articles")
    print("\n  Foreign keys on cookbook_reflect_articles:")
    for fk in fks:
        print(f"    {fk['constrained_columns']} → {fk['referred_table']}.{fk['referred_columns']}")


def reflect_indexes(engine) -> None:
    """Inspect indexes."""
    print("\n=== Reflect Indexes ===")
    insp = inspect(engine)

    indexes = insp.get_indexes("cookbook_reflect_articles")
    print("  Indexes on cookbook_reflect_articles:")
    for idx in indexes:
        unique = " (UNIQUE)" if idx.get("unique") else ""
        print(f"    {idx['name']:30s}  columns={idx['column_names']}{unique}")


def autoload_table(engine) -> None:
    """Reflect and use a table without defining it in Python."""
    print("\n=== Autoload Table ===")
    metadata = MetaData()

    # Reflect the table from database
    authors = Table("cookbook_reflect_authors", metadata, autoload_with=engine)

    print(f"  Reflected 'cookbook_reflect_authors' with {len(authors.columns)} columns:")
    for col in authors.columns:
        print(f"    • {col.name}: {col.type}")

    # Use the reflected table for queries
    with engine.connect() as conn:
        from sqlalchemy import insert as sa_insert

        conn.execute(sa_insert(authors).values(name="Test Author", country="US"))
        conn.commit()

        from sqlalchemy import select

        result = conn.execute(select(authors))
        rows = result.fetchall()
        print(f"\n  Queried {len(rows)} row(s) from reflected table:")
        for row in rows:
            print(f"    id={row.id}, name={row.name}, country={row.country}")


def cleanup(engine) -> None:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    for table_name in ["cookbook_reflect_articles", "cookbook_reflect_authors"]:
        if table_name in metadata.tables:
            metadata.tables[table_name].drop(engine)
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    try:
        setup(engine)
        list_tables(engine)
        reflect_columns(engine)
        reflect_constraints(engine)
        reflect_indexes(engine)
        autoload_table(engine)
    finally:
        cleanup(engine)
        engine.dispose()
