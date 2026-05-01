"""Write pandas DataFrames to CUBRID using to_sql replace and append modes."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TABLE_NAME = "cookbook_to_sql_demo"


def main() -> int:
    engine = create_engine(DATABASE_URL)

    base_df = pd.DataFrame(
        [
            {"item_id": 1, "item_name": "Notebook", "stock_qty": 10, "unit_cost_cents": 3200},
            {"item_id": 2, "item_name": "Mouse", "stock_qty": 25, "unit_cost_cents": 1500},
            {"item_id": 3, "item_name": "Keyboard", "stock_qty": 14, "unit_cost_cents": 2800},
        ]
    )
    append_df = pd.DataFrame(
        [
            {"item_id": 4, "item_name": "Monitor", "stock_qty": 6, "unit_cost_cents": 19800},
            {"item_id": 5, "item_name": "Webcam", "stock_qty": 9, "unit_cost_cents": 6400},
        ]
    )

    try:
        with engine.begin() as conn:
            _ = conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))

        print("=== Base DataFrame (replace) ===")
        print(base_df)
        _ = base_df.to_sql(TABLE_NAME, engine, if_exists="replace", index=False)

        print("\n=== Append DataFrame (append) ===")
        print(append_df)
        _ = append_df.to_sql(TABLE_NAME, engine, if_exists="append", index=False)

        final_df = pd.read_sql(TABLE_NAME, engine)
        final_df["unit_cost_dollars"] = final_df["unit_cost_cents"] / 100

        print("\n=== Final table after replace + append ===")
        print(final_df)
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
