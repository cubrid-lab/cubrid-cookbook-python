"""Run a filtered SQL query with safe parameter binding via sqlalchemy.text and pandas."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_orders"


def main() -> int:
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
            _ = conn.execute(
                text(
                    f"""
                    CREATE TABLE {TABLE_NAME} (
                        order_id INTEGER PRIMARY KEY,
                        customer_name VARCHAR(80) NOT NULL,
                        region_name VARCHAR(20) NOT NULL,
                        order_total_cents INTEGER NOT NULL,
                        is_priority INTEGER NOT NULL
                    )
                    """
                )
            )
            _ = conn.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (order_id, customer_name, region_name, order_total_cents, is_priority)
                    VALUES
                        (1, 'Alice', 'north', 5200, 0),
                        (2, 'Bob', 'west', 15400, 1),
                        (3, 'Cara', 'north', 8600, 1),
                        (4, 'Dion', 'south', 4300, 0),
                        (5, 'Evan', 'west', 21200, 1),
                        (6, 'Faye', 'east', 9400, 0),
                        (7, 'Gina', 'north', 12800, 1),
                        (8, 'Hugo', 'south', 6700, 0)
                    """
                )
            )

        query = text(
            f"""
            SELECT order_id, customer_name, region_name, order_total_cents, is_priority
            FROM {TABLE_NAME}
            WHERE region_name = :region_name
              AND order_total_cents >= :min_total_cents
            ORDER BY order_total_cents DESC
            """
        )
        params = {"region_name": "north", "min_total_cents": 7000}

        print("=== read_sql_query with parameters ===")
        filtered_df = pd.read_sql_query(query, engine, params=params)
        print(filtered_df)

        print("\n=== Result with dollars column ===")
        filtered_df["order_total_dollars"] = filtered_df["order_total_cents"] / 100
        print(filtered_df[["order_id", "customer_name", "order_total_dollars", "is_priority"]])
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
