"""05_dml_extensions.py — CUBRID-specific DML extensions.

Demonstrates:
- ON DUPLICATE KEY UPDATE (upsert)
- MERGE statement
- REPLACE INTO
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from sqlalchemy_cubrid import insert, merge, replace

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = "cookbook_config"

    config_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    val: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(500), default=None)

    def __repr__(self) -> str:
        return f"Config(config_key='{self.config_key}', val='{self.val}')"


class Counter(Base):
    __tablename__ = "cookbook_dml_counters"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    cnt: Mapped[int] = mapped_column(default=0)

    def __repr__(self) -> str:
        return f"Counter(name='{self.name}', cnt={self.cnt})"


def setup(engine) -> None:
    print("=== DML Extensions — Setup ===")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("  ✓ Created tables")


def show_configs(session: Session) -> None:
    rows = session.scalars(select(Config).order_by(Config.config_key)).all()
    for r in rows:
        print(f"    {r.config_key:20s} = {r.val:20s}  ({r.description or ''})")


def on_duplicate_key_update_example(engine) -> None:
    """ON DUPLICATE KEY UPDATE — upsert pattern.

    INSERT INTO ... ON DUPLICATE KEY UPDATE ...
    If the row exists (by PK/UNIQUE), update it. Otherwise, insert it.
    """
    print("\n=== ON DUPLICATE KEY UPDATE ===")

    with Session(engine) as session:
        # Initial insert
        stmt = insert(Config).values(
            config_key="app.name",
            val="CUBRID Cookbook",
            description="Application name",
        )
        session.execute(stmt)
        session.commit()
        print("  Initial insert:")
        show_configs(session)

        # Upsert — same key, different value
        stmt = (
            insert(Config)
            .values(
                config_key="app.name",
                val="CUBRID Cookbook v2",
                description="Updated application name",
            )
            .on_duplicate_key_update(
                val="CUBRID Cookbook v2",
                description="Updated application name",
            )
        )
        session.execute(stmt)
        session.commit()
        print("\n  After ODKU (updated value):")
        show_configs(session)

        # Upsert — new key (inserts)
        stmt = (
            insert(Config)
            .values(
                config_key="app.version",
                val="1.0.0",
                description="Application version",
            )
            .on_duplicate_key_update(val="1.0.0")
        )
        session.execute(stmt)
        session.commit()
        print("\n  After ODKU (new key inserted):")
        show_configs(session)


def replace_example(engine) -> None:
    """REPLACE INTO — delete + insert if exists.

    Unlike ON DUPLICATE KEY UPDATE, REPLACE deletes the existing row first,
    then inserts the new one. This means all columns get new values.
    """
    print("\n=== REPLACE INTO ===")

    with Session(engine) as session:
        # Insert initial config
        stmt = replace(Config).values(
            config_key="db.host",
            val="localhost",
            description="Database host",
        )
        session.execute(stmt)
        session.commit()
        print("  Initial REPLACE (insert):")
        show_configs(session)

        # Replace existing — deletes old row, inserts new
        stmt = replace(Config).values(
            config_key="db.host",
            val="production.db.local",
            description="Production database host",
        )
        session.execute(stmt)
        session.commit()
        print("\n  After REPLACE (replaced):")
        show_configs(session)


def merge_example(engine) -> None:
    """MERGE — conditional insert/update in one statement.

    MERGE INTO target USING source ON (condition)
    WHEN MATCHED THEN UPDATE SET ...
    WHEN NOT MATCHED THEN INSERT (...) VALUES (...)

    Requires a source table. We create a staging table to demonstrate.
    """
    print("\n=== MERGE Statement ===")

    # Create a staging table for the source data
    staging_metadata = MetaData()
    counter_source = Table(
        "cookbook_counter_staging",
        staging_metadata,
        Column("name", String(100), primary_key=True),
        Column("cnt", Integer, default=0),
    )
    staging_metadata.drop_all(engine)
    staging_metadata.create_all(engine)

    with engine.begin() as conn:
        # Seed target counters
        conn.execute(text("DELETE FROM cookbook_dml_counters"))
        conn.execute(insert(Counter).values(name="page_views", cnt=100))
        conn.execute(insert(Counter).values(name="api_calls", cnt=50))

    with Session(engine) as session:
        print("  Initial counters:")
        for c in session.scalars(select(Counter).order_by(Counter.name)).all():
            print(f"    {c.name}: {c.cnt}")

    with engine.begin() as conn:
        # Populate staging table with updates + new entries
        from sqlalchemy import insert as sa_insert

        conn.execute(
            sa_insert(counter_source),
            [
                {"name": "page_views", "cnt": 10},  # exists → update
                {"name": "api_calls", "cnt": 5},  # exists → update
                {"name": "errors", "cnt": 1},  # new → insert
            ],
        )

        # Get the Counter table object for Core-level merge
        counters_table = Counter.__table__

        # MERGE: update matched rows, insert unmatched rows
        stmt = (
            merge(counters_table)
            .using(counter_source)
            .on(counters_table.c.name == counter_source.c.name)
            .when_matched_then_update({"cnt": counters_table.c.cnt + counter_source.c.cnt})
            .when_not_matched_then_insert(
                {
                    counters_table.c.name: counter_source.c.name,
                    counters_table.c.cnt: counter_source.c.cnt,
                }
            )
        )
        conn.execute(stmt)

    with Session(engine) as session:
        print("\n  After MERGE (increment existing, insert new):")
        for c in session.scalars(select(Counter).order_by(Counter.name)).all():
            print(f"    {c.name}: {c.cnt}")

    # Clean up staging
    staging_metadata.drop_all(engine)


def cleanup(engine) -> None:
    Base.metadata.drop_all(engine)
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)

    try:
        setup(engine)
        on_duplicate_key_update_example(engine)
        replace_example(engine)
        merge_example(engine)
    finally:
        cleanup(engine)
        engine.dispose()
