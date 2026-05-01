"""Query CUBRID data with pandas, build summary stats, and export results to CSV."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_monthly_sales"
OUTPUT_FILE = Path("cookbook_monthly_sales_summary.csv")


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
                        sale_month VARCHAR(7) NOT NULL,
                        category_name VARCHAR(40) NOT NULL,
                        revenue_cents INTEGER NOT NULL,
                        is_promo INTEGER NOT NULL
                    )
                    """
                )
            )
            _ = conn.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (sale_id, sale_month, category_name, revenue_cents, is_promo)
                    VALUES
                        (1, '2026-01', 'electronics', 189900, 1),
                        (2, '2026-01', 'electronics', 24900, 0),
                        (3, '2026-01', 'furniture', 56700, 0),
                        (4, '2026-01', 'accessories', 39500, 1),
                        (5, '2026-02', 'electronics', 129900, 0),
                        (6, '2026-02', 'furniture', 37800, 1),
                        (7, '2026-02', 'accessories', 31600, 0),
                        (8, '2026-02', 'office', 25200, 1),
                        (9, '2026-03', 'electronics', 259800, 1),
                        (10, '2026-03', 'furniture', 18900, 0),
                        (11, '2026-03', 'accessories', 23700, 0),
                        (12, '2026-03', 'office', 16800, 1)
                    """
                )
            )

        df = pd.read_sql(
            text(
                f"""
                SELECT sale_month, category_name, revenue_cents, is_promo
                FROM {TABLE_NAME}
                ORDER BY sale_month, category_name
                """
            ),
            engine,
        )
        df["revenue_dollars"] = df["revenue_cents"] / 100
        df["is_promo"] = df["is_promo"].map({0: False, 1: True})

        summary_df = (
            df.groupby(["sale_month", "category_name"], as_index=False)
            .agg(
                total_revenue_cents=("revenue_cents", "sum"),
                avg_revenue_cents=("revenue_cents", "mean"),
                row_cnt=("category_name", "count"),
            )
            .sort_values(["sale_month", "total_revenue_cents"], ascending=[True, False])
        )
        summary_df["total_revenue_dollars"] = summary_df["total_revenue_cents"] / 100
        summary_df["avg_revenue_dollars"] = summary_df["avg_revenue_cents"] / 100

        try:
            summary_df.to_csv(OUTPUT_FILE, index=False)
        except IOError as io_exc:
            print(f"CSV export error: {io_exc}")
            return 1

        print("=== Source DataFrame ===")
        print(df)
        print("\n=== Summary DataFrame ===")
        print(summary_df)
        print("\n=== Summary stats ===")
        print(summary_df[["total_revenue_dollars", "avg_revenue_dollars"]].describe())
        print(f"\nCSV exported to: {OUTPUT_FILE.resolve()}")
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
