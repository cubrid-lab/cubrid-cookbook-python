"""Streamlit recipe: KPI metric cards from SQL COUNT, SUM, and AVG aggregates."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
PRODUCTS_TABLE = "cookbook_products"
SALES_TABLE = "cookbook_sales"


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(DATABASE_URL)


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
            start = date(2026, 1, 1)
            sales_rows = [
                {
                    "product_id": ((i % 10) + 1),
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

    ensure_data(reset=False)
    if st.button("Reset Demo Data"):
        ensure_data(reset=True)
        st.success("Demo tables recreated and reseeded.")

    kpis = fetch_kpis()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sales Rows", f"{int(kpis['sales_rows']):,}")
    col2.metric("Gross Revenue", f"${kpis['gross_revenue_cents'] / 100:,.2f}")
    col3.metric("Average Unit Price", f"${kpis['avg_unit_price_cents'] / 100:,.2f}")
    col4.metric("Products Sold", f"{int(kpis['active_products']):,}")


if __name__ == "__main__":
    main()
