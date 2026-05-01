"""Create a grouped category and region report using pandas groupby and aggregation."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_sales_report"


def main() -> int:
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
            _ = conn.execute(
                text(
                    f"""
                    CREATE TABLE {TABLE_NAME} (
                        sale_id INTEGER PRIMARY KEY,
                        category_name VARCHAR(40) NOT NULL,
                        region_name VARCHAR(20) NOT NULL,
                        quantity_val INTEGER NOT NULL,
                        revenue_cents INTEGER NOT NULL
                    )
                    """
                )
            )
            _ = conn.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (sale_id, category_name, region_name, quantity_val, revenue_cents)
                    VALUES
                        (1, 'electronics', 'north', 2, 259800),
                        (2, 'electronics', 'west', 1, 129900),
                        (3, 'furniture', 'west', 3, 56700),
                        (4, 'furniture', 'south', 1, 18900),
                        (5, 'accessories', 'north', 4, 31600),
                        (6, 'accessories', 'east', 5, 39500),
                        (7, 'office', 'south', 6, 25200),
                        (8, 'office', 'west', 2, 8400),
                        (9, 'electronics', 'north', 1, 24900),
                        (10, 'furniture', 'west', 2, 37800),
                        (11, 'accessories', 'east', 3, 23700),
                        (12, 'office', 'north', 4, 16800)
                    """
                )
            )

        df = pd.read_sql(TABLE_NAME, engine)
        print("=== Source sales rows ===")
        print(df)

        report_df = (
            df.groupby(["category_name", "region_name"], as_index=False)
            .agg(
                quantity_sum=("quantity_val", "sum"),
                revenue_sum_cents=("revenue_cents", "sum"),
                revenue_mean_cents=("revenue_cents", "mean"),
                sale_cnt=("sale_id", "count"),
            )
            .sort_values(["revenue_sum_cents", "sale_cnt"], ascending=[False, False])
        )
        report_df["revenue_sum_dollars"] = report_df["revenue_sum_cents"] / 100
        report_df["revenue_mean_dollars"] = report_df["revenue_mean_cents"] / 100

        print("\n=== Groupby report (category + region) ===")
        print(report_df)
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
