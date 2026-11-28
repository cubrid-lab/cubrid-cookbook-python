"""Streamlit recipe: KPI metric cards from SQL COUNT, SUM, and AVG aggregates."""

from __future__ import annotations

from datetime import date, timedelta

import os
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DATABASE_URL = os.environ.get("DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb")
PRODUCTS_TABLE = "cookbook_dashboard_products"
SALES_TABLE = "cookbook_dashboard_sales"
DEMO_PRODUCT_NAMES = (
    "Laptop 14",
    "Wireless Mouse",
    "Desk Lamp",
    "Office Chair",
    "Notebook Pack",
    "Tea Kettle",
    "Fitness Band",
    "Water Bottle",
    "Monitor 27",
    "Standing Desk",
)


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(DATABASE_URL)


class DemoDataError(RuntimeError):
    """The demo products cannot be identified, so sample sales are not seeded."""


def _demo_product_ids(connection) -> list[int]:
    """Return the real IDs of the ten demo products, in the order they are seeded.

    AUTO_INCREMENT values do not restart at 1 after earlier inserts and deletes, so sales
    must reference the IDs CUBRID actually assigned. The demo products are found by name,
    so unrelated rows in the table are never used; if a demo product is missing, renamed
    or ambiguous, nothing is seeded and the error says how to recover.
    """
    ids: list[int] = []
    problems: list[str] = []
    for name in DEMO_PRODUCT_NAMES:
        found = [
            int(row[0])
            for row in connection.execute(
                text(f"SELECT product_id FROM {PRODUCTS_TABLE} WHERE product_name = :name"),
                {"name": name},
            )
        ]
        if len(found) == 1:
            ids.append(found[0])
        else:
            problems.append(f"{name!r} ({'missing' if not found else f'{len(found)} rows'})")
    if problems:
        raise DemoDataError(
            "Cannot seed sample sales: the demo products "
            + ", ".join(problems)
            + " cannot be identified in "
            + f"{PRODUCTS_TABLE}. Restore them or use Reset Demo Data."
        )
    return ids


def ensure_data(reset: bool = False) -> None:
    with get_engine().begin() as connection:
        if reset:
            connection.execute(text(f"DROP TABLE IF EXISTS {SALES_TABLE}"))
            connection.execute(text(f"DROP TABLE IF EXISTS {PRODUCTS_TABLE}"))

        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {PRODUCTS_TABLE} (
                    product_id INTEGER AUTO_INCREMENT PRIMARY KEY,
                    product_name VARCHAR(100) NOT NULL,
                    category_name VARCHAR(50) NOT NULL,
                    unit_price_cents INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {SALES_TABLE} (
                    sale_id INTEGER AUTO_INCREMENT PRIMARY KEY,
                    product_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    sale_date DATE NOT NULL,
                    FOREIGN KEY (product_id) REFERENCES {PRODUCTS_TABLE}(product_id)
                )
                """
            )
        )

        products_total = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}")).scalar_one()
        )
        if products_total == 0:
            connection.execute(
                text(
                    f"""
                    INSERT INTO {PRODUCTS_TABLE} (product_name, category_name, unit_price_cents, is_active)
                    VALUES (:product_name, :category_name, :unit_price_cents, :is_active)
                    """
                ),
                [
                    {
                        "product_name": "Laptop 14",
                        "category_name": "Electronics",
                        "unit_price_cents": 109900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Wireless Mouse",
                        "category_name": "Electronics",
                        "unit_price_cents": 3900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Desk Lamp",
                        "category_name": "Home",
                        "unit_price_cents": 2900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Office Chair",
                        "category_name": "Office",
                        "unit_price_cents": 17900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Notebook Pack",
                        "category_name": "Office",
                        "unit_price_cents": 1200,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Tea Kettle",
                        "category_name": "Home",
                        "unit_price_cents": 5400,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Fitness Band",
                        "category_name": "Lifestyle",
                        "unit_price_cents": 12900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Water Bottle",
                        "category_name": "Lifestyle",
                        "unit_price_cents": 1500,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Monitor 27",
                        "category_name": "Electronics",
                        "unit_price_cents": 21900,
                        "is_active": 1,
                    },
                    {
                        "product_name": "Standing Desk",
                        "category_name": "Office",
                        "unit_price_cents": 35900,
                        "is_active": 0,
                    },
                ],
            )

        sales_total = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {SALES_TABLE}")).scalar_one()
        )
        if sales_total == 0:
            product_ids = _demo_product_ids(connection)
            start = date(2026, 1, 1)
            sales_rows = [
                {
                    "product_id": product_ids[i % len(product_ids)],
                    "quantity": ((i % 5) + 1),
                    "sale_date": start + timedelta(days=i),
                }
                for i in range(15)
            ]
            connection.execute(
                text(
                    f"INSERT INTO {SALES_TABLE} (product_id, quantity, sale_date) VALUES (:product_id, :quantity, :sale_date)"
                ),
                sales_rows,
            )


def fetch_kpis() -> dict[str, float]:
    sql = text(
        f"""
        SELECT
            COUNT(*) AS sales_rows,
            COALESCE(SUM(s.quantity * p.unit_price_cents), 0) AS gross_revenue_cents,
            COALESCE(AVG(p.unit_price_cents), 0) AS avg_unit_price_cents,
            COUNT(DISTINCT s.product_id) AS active_products
        FROM {SALES_TABLE} s
        JOIN {PRODUCTS_TABLE} p ON p.product_id = s.product_id
        """
    )
    with get_engine().connect() as connection:
        row = connection.execute(sql).mappings().one()
    return {
        "sales_rows": float(row["sales_rows"]),
        "gross_revenue_cents": float(row["gross_revenue_cents"]),
        "avg_unit_price_cents": float(row["avg_unit_price_cents"]),
        "active_products": float(row["active_products"]),
    }


def main() -> None:
    st.set_page_config(page_title="03 KPIs", layout="wide")
    st.title("03 KPIs")
    st.caption("KPI cards using st.metric + SQL COUNT/SUM/AVG from cookbook_ tables.")

    seed_error = None
    try:
        ensure_data(reset=False)
    except DemoDataError as exc:
        # Keep the explicit reset action reachable; nothing is reset automatically.
        seed_error = exc
    if st.button("Reset Demo Data"):
        ensure_data(reset=True)
        seed_error = None
        st.success("Demo tables recreated and reseeded.")
    if seed_error is not None:
        st.error(str(seed_error))
        st.stop()

    kpis = fetch_kpis()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sales Rows", f"{int(kpis['sales_rows']):,}")
    col2.metric("Gross Revenue", f"${kpis['gross_revenue_cents'] / 100:,.2f}")
    col3.metric("Average Unit Price", f"${kpis['avg_unit_price_cents'] / 100:,.2f}")
    col4.metric("Products Sold", f"{int(kpis['active_products']):,}")


if __name__ == "__main__":
    main()
