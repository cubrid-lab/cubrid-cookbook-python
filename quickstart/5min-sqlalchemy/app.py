from __future__ import annotations

from sqlalchemy import (
    Integer,
    MetaData,
    String,
    Table,
    Column,
    bindparam,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"

metadata = MetaData()

core_items = Table(
    "cookbook_core_items",
    metadata,
    Column("item_id", Integer, primary_key=True, autoincrement=True),
    Column("item_name", String(100), nullable=False),
    Column("val", String(255), nullable=False),
)


class Base(DeclarativeBase):
    pass


class CookbookOrmItem(Base):
    __tablename__ = "cookbook_orm_items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    val: Mapped[str] = mapped_column(String(255), nullable=False)


def run_core_crud(engine) -> None:
    print("=== SQLAlchemy Core CRUD ===")
    with engine.begin() as conn:
        insert_stmt = insert(core_items).values(
            item_name=bindparam("item_name"),
            val=bindparam("val"),
        )
        conn.execute(insert_stmt, {"item_name": "core-sample", "val": "v1"})

        query_stmt = select(core_items.c.item_id, core_items.c.item_name, core_items.c.val).where(
            core_items.c.item_name == bindparam("search_item_name")
        )
        rows = conn.execute(query_stmt, {"search_item_name": "core-sample"}).all()
        print("Core query result:", rows)

        update_stmt = (
            update(core_items)
            .where(core_items.c.item_name == bindparam("update_item_name"))
            .values(val=bindparam("new_val"))
        )
        conn.execute(update_stmt, {"update_item_name": "core-sample", "new_val": "v2"})

        delete_stmt = delete(core_items).where(
            core_items.c.item_name == bindparam("delete_item_name")
        )
        conn.execute(delete_stmt, {"delete_item_name": "core-sample"})


def run_orm_crud(engine) -> None:
    print("\n=== SQLAlchemy ORM CRUD ===")

    with Session(engine) as session:
        with session.begin():
            orm_item = CookbookOrmItem(item_name="orm-sample", val="v1")
            session.add(orm_item)

    with Session(engine) as session:
        query_stmt = select(CookbookOrmItem).where(
            CookbookOrmItem.item_name == bindparam("search_item_name")
        )
        found = session.execute(query_stmt, {"search_item_name": "orm-sample"}).scalar_one_or_none()
        print(
            "ORM query result:",
            found.item_id if found else None,
            found.item_name if found else None,
        )

        if found is None:
            return

    with Session(engine) as session:
        with session.begin():
            to_update = session.execute(
                select(CookbookOrmItem).where(
                    CookbookOrmItem.item_name == bindparam("update_item_name")
                ),
                {"update_item_name": "orm-sample"},
            ).scalar_one_or_none()
            if to_update is not None:
                to_update.val = "v2"

    with Session(engine) as session:
        with session.begin():
            to_delete = session.execute(
                select(CookbookOrmItem).where(
                    CookbookOrmItem.item_name == bindparam("delete_item_name")
                ),
                {"delete_item_name": "orm-sample"},
            ).scalar_one_or_none()
            if to_delete is not None:
                session.delete(to_delete)


def main() -> int:
    engine = create_engine(DATABASE_URL)

    try:
        metadata.drop_all(engine)
        Base.metadata.drop_all(engine)
        metadata.create_all(engine)
        Base.metadata.create_all(engine)
        run_core_crud(engine)
        run_orm_crud(engine)
        print("\nDone. Core and ORM CRUD completed successfully.")
        return 0
    except SQLAlchemyError as exc:
        print(f"Database operation failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1
    finally:
        # Leave the database as it was found, even after a failure.
        # Each table set is dropped on its own, so one failure leaves no other table.
        for tables in (metadata, Base.metadata):
            try:
                tables.drop_all(engine)
            except SQLAlchemyError as exc:
                print(f"Cleanup failed: {exc}")
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
