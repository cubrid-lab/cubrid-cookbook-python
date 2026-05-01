"""Clean and transform raw order rows using pandas rename, assign, and apply patterns."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_raw_orders"


def priority_label(priority_flag: object) -> str:
    return "priority" if bool(priority_flag) else "standard"


def main() -> int:
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
            _ = conn.execute(
                text(
                    f"""
                    CREATE TABLE {TABLE_NAME} (
                        record_id INTEGER PRIMARY KEY,
                        customer_name VARCHAR(80) NOT NULL,
                        region_name VARCHAR(20) NOT NULL,
                        amount_cents INTEGER NOT NULL,
                        priority_flag INTEGER NOT NULL
                    )
                    """
                )
            )
            _ = conn.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (record_id, customer_name, region_name, amount_cents, priority_flag)
                    VALUES
                        (1, 'Alice', 'north', 5200, 0),
                        (2, 'Bob', 'west', 15400, 1),
                        (3, 'Cara', 'north', 8600, 1),
                        (4, 'Dion', 'south', 4300, 0),
                        (5, 'Evan', 'west', 21200, 1),
                        (6, 'Faye', 'east', 9400, 0),
                        (7, 'Gina', 'north', 12800, 1),
                        (8, 'Hugo', 'south', 6700, 0),
                        (9, 'Iris', 'east', 11100, 1),
                        (10, 'Jade', 'west', 4900, 0)
                    """
                )
            )

        raw_df = pd.read_sql(TABLE_NAME, engine)
        print("=== Raw data ===")
        print(raw_df)

        cleaned_df = raw_df.rename(
            columns={
                "record_id": "order_id",
                "amount_cents": "order_total_cents",
                "priority_flag": "is_priority",
            }
        ).assign(
            order_total_dollars=lambda frame: frame["order_total_cents"] / 100,
            is_priority=lambda frame: frame["is_priority"].map({0: False, 1: True}),
        )
        priority_series = cleaned_df["is_priority"]
        cleaned_df["service_tier"] = priority_series.apply(priority_label)

        print("\n=== Cleaned and transformed data ===")
        print(cleaned_df)
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
