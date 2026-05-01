"""Streamlit recipe: grouped bar and line charts with native Streamlit chart APIs."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
PRODUCTS_TABLE = "cookbook_products"
SALES_TABLE = "cookbook_sales"


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(DATABASE_URL)


def initialize(reset: bool = False) -> None:
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


def load_grouped_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    by_category_sql = text(
        f"""
        SELECT
            p.category_name,
            SUM(s.quantity * p.unit_price_cents) AS revenue_cents
        FROM {SALES_TABLE} s
        JOIN {PRODUCTS_TABLE} p ON p.product_id = s.product_id
        GROUP BY p.category_name
        ORDER BY p.category_name
        """
    )
    by_date_sql = text(
        f"""
        SELECT
            s.sale_date,
            SUM(s.quantity * p.unit_price_cents) AS revenue_cents,
            SUM(s.quantity) AS units_sold
        FROM {SALES_TABLE} s
        JOIN {PRODUCTS_TABLE} p ON p.product_id = s.product_id
        GROUP BY s.sale_date
        ORDER BY s.sale_date
        """
    )
    with get_engine().connect() as connection:
        by_category = pd.read_sql_query(by_category_sql, connection)
        by_date = pd.read_sql_query(by_date_sql, connection)
    by_date["sale_date"] = pd.to_datetime(by_date["sale_date"])
    return by_category, by_date


def main() -> None:
    st.set_page_config(page_title="04 Charts", layout="wide")
    st.title("04 Charts")
    st.caption("Bar and line charts from grouped SQL queries using st.bar_chart and st.line_chart.")

    initialize(reset=False)
    if st.button("Reset Demo Data"):
        initialize(reset=True)
        st.success("Demo tables recreated and reseeded.")

    category_df, day_df = load_grouped_data()
    left, right = st.columns(2)

    with left:
        st.subheader("Revenue by Category")
        st.bar_chart(category_df.set_index("category_name")["revenue_cents"] / 100)

    with right:
        st.subheader("Revenue and Units by Day")
        line_df = day_df.set_index("sale_date")
        line_df["revenue_usd"] = line_df["revenue_cents"] / 100
        st.line_chart(line_df[["revenue_usd", "units_sold"]])

    st.dataframe(day_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
