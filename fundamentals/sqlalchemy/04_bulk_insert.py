"""04_bulk_insert.py - Bulk insert patterns with SQLAlchemy ORM and Core DML.

Demonstrates:
- Fast bulk insert via session.execute(insert(...), rows)
- ORM add_all insert flow
- Simple timing comparison between both approaches
- Integer cents for money and Integer 0/1 for boolean-like flags
"""

from __future__ import annotations

from time import perf_counter
from typing import final

from sqlalchemy import Integer, String, create_engine, func, insert, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


@final
class Product(Base):
    __tablename__ = "cookbook_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_code: Mapped[str] = mapped_column(String(40), unique=True)
    product_name: Mapped[str] = mapped_column(String(120))
    price_cents: Mapped[int] = mapped_column(Integer)
    in_stock_flag: Mapped[int] = mapped_column(Integer, default=1)


def build_rows(prefix: str, size: int) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for idx in range(size):
        rows.append(
            {
                "sku_code": f"{prefix}-{idx:04d}",
                "product_name": f"Product {prefix} {idx}",
                "price_cents": 1000 + (idx % 50) * 25,
                "in_stock_flag": 1 if idx % 3 else 0,
            }
        )
    return rows


def main() -> None:
    engine = create_engine(DATABASE_URL)
    print("=== Bulk Insert Comparison ===")

    try:
        Base.metadata.create_all(engine)
        print("[1] Created table cookbook_products")

        fast_rows = build_rows("FAST", 500)
        orm_rows = build_rows("ORM", 500)

        with Session(engine) as session:
            print("\n[2] Bulk insert using session.execute(insert(...), rows)")
            start = perf_counter()
            _ = session.execute(insert(Product), fast_rows)
            session.commit()
            fast_elapsed = perf_counter() - start
            print(f"Inserted {len(fast_rows)} rows in {fast_elapsed:.4f} seconds")

            print("\n[3] Bulk insert using ORM add_all")
            orm_objects = [Product(**row) for row in orm_rows]
            start = perf_counter()
            session.add_all(orm_objects)
            session.commit()
            orm_elapsed = perf_counter() - start
            print(f"Inserted {len(orm_objects)} rows in {orm_elapsed:.4f} seconds")

            print("\n[4] Verify row count and sample data")
            total_rows = session.scalar(select(func.count(Product.id)))
            print(f"Total rows in cookbook_products: {total_rows}")

            sample = session.scalars(select(Product).order_by(Product.id).limit(5)).all()
            for product in sample:
                dollars = product.price_cents / 100
                print(
                    f"id={product.id}, sku={product.sku_code}, price_cents={product.price_cents} (${dollars:.2f}), in_stock_flag={product.in_stock_flag}"
                )

            print("\n[5] Timing summary")
            print(f"execute(insert, rows): {fast_elapsed:.4f}s")
            print(f"add_all: {orm_elapsed:.4f}s")

        print("\nBulk insert demo completed.")
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
