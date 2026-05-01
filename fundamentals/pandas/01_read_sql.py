"""Load a full CUBRID table into a pandas DataFrame with pd.read_sql."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_products"


def main() -> int:
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
            _ = conn.execute(
                text(
                    f"""
                    CREATE TABLE {TABLE_NAME} (
                        product_id INTEGER PRIMARY KEY,
                        product_name VARCHAR(80) NOT NULL,
                        category_name VARCHAR(40) NOT NULL,
                        unit_price_cents INTEGER NOT NULL,
                        is_active INTEGER NOT NULL
                    )
                    """
                )
            )
            _ = conn.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (product_id, product_name, category_name, unit_price_cents, is_active)
                    VALUES
                        (1, 'Notebook Pro 14', 'electronics', 129900, 1),
                        (2, 'Office Chair', 'furniture', 18900, 1),
                        (3, 'Noise-Cancel Headset', 'electronics', 24900, 1),
                        (4, 'Desk Lamp', 'office', 4200, 0),
                        (5, 'Backpack', 'accessories', 7900, 1),
                        (6, 'Water Bottle', 'accessories', 2400, 1)
                    """
                )
            )

        print("=== read_sql with table name ===")
        df = pd.read_sql(TABLE_NAME, engine)
        print(df)

        print("\n=== dtypes ===")
        print(df.dtypes)

        print("\n=== head(3) ===")
        print(df.head(3))
        return 0
    except SQLAlchemyError as exc:
        print(f"Database error: {exc}")
        return 1
    finally:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
