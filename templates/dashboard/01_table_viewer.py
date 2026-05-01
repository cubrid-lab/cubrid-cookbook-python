"""Streamlit recipe: live table viewer with auto-refresh against CUBRID."""

from __future__ import annotations

import time
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


def create_tables(connection) -> None:
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


def seed_if_empty(connection) -> None:
    product_count = connection.execute(text(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}")).scalar_one()
    if int(product_count) == 0:
        products = [
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
        ]
        connection.execute(
            text(
                f"""
                INSERT INTO {PRODUCTS_TABLE}
                    (product_name, category_name, unit_price_cents, is_active)
                VALUES
                    (:product_name, :category_name, :unit_price_cents, :is_active)
                """
            ),
            products,
        )

    sales_count = connection.execute(text(f"SELECT COUNT(*) FROM {SALES_TABLE}")).scalar_one()
    if int(sales_count) == 0:
        base = date(2026, 1, 1)
        sales = [
            {
                "product_id": ((i % 10) + 1),
                "quantity": ((i % 5) + 1),
                "sale_date": base + timedelta(days=i),
            }
            for i in range(15)
        ]
        connection.execute(
            text(
                f"INSERT INTO {SALES_TABLE} (product_id, quantity, sale_date) VALUES (:product_id, :quantity, :sale_date)"
            ),
            sales,
        )


def reset_demo_data() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {SALES_TABLE}"))
        connection.execute(text(f"DROP TABLE IF EXISTS {PRODUCTS_TABLE}"))
        create_tables(connection)
        seed_if_empty(connection)


def ensure_data() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        create_tables(connection)
        seed_if_empty(connection)


def load_table() -> pd.DataFrame:
    sql = text(
        f"""
        SELECT
            s.sale_id,
            s.sale_date,
            p.product_name,
            p.category_name,
            s.quantity,
            p.unit_price_cents,
            s.quantity * p.unit_price_cents AS total_cents,
            p.is_active
        FROM {SALES_TABLE} s
        JOIN {PRODUCTS_TABLE} p ON p.product_id = s.product_id
        ORDER BY s.sale_date DESC, s.sale_id DESC
        """
    )
    with get_engine().connect() as connection:
        return pd.read_sql_query(sql, connection)


def main() -> None:
    st.set_page_config(page_title="01 Table Viewer", layout="wide")
    st.title("01 Table Viewer")
    st.caption("Live query display with manual Refresh button (no auto-refresh).")

    ensure_data()

    if st.button("Reset Demo Data"):
        reset_demo_data()
        st.success("Demo tables recreated and reseeded.")

    df = load_table()
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"Rows shown: {len(df)}")

    if st.button("🔄 Refresh"):
        st.rerun()


if __name__ == "__main__":
    main()
