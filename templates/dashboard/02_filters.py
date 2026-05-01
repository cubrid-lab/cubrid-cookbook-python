"""Streamlit recipe: sidebar category and price filters with dynamic SQL WHERE clauses."""

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


def setup_schema(seed_only: bool = False) -> None:
    with get_engine().begin() as connection:
        if not seed_only:
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

        count_products = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}")).scalar_one()
        )
        if count_products == 0:
            connection.execute(
                text(
                    f"""
                    INSERT INTO {PRODUCTS_TABLE}
                        (product_name, category_name, unit_price_cents, is_active)
                    VALUES
                        (:product_name, :category_name, :unit_price_cents, :is_active)
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

        count_sales = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {SALES_TABLE}")).scalar_one()
        )
        if count_sales == 0:
            start = date(2026, 1, 1)
            sales_rows = [
                {
                    "product_id": ((i % 10) + 1),
                    "quantity": ((i % 4) + 1),
                    "sale_date": start + timedelta(days=i),
                }
                for i in range(12)
            ]
            connection.execute(
                text(
                    f"INSERT INTO {SALES_TABLE} (product_id, quantity, sale_date) VALUES (:product_id, :quantity, :sale_date)"
                ),
                sales_rows,
            )


def fetch_filtered(category_name: str, min_cents: int, max_cents: int) -> pd.DataFrame:
    where_parts: list[str] = ["p.unit_price_cents BETWEEN :min_cents AND :max_cents"]
    params: dict[str, int | str] = {"min_cents": min_cents, "max_cents": max_cents}
    if category_name != "All":
        where_parts.append("p.category_name = :category_name")
        params["category_name"] = category_name

    where_sql = " AND ".join(where_parts)
    sql = text(
        f"""
        SELECT
            s.sale_id,
            s.sale_date,
            p.product_name,
            p.category_name,
            p.unit_price_cents,
            s.quantity,
            s.quantity * p.unit_price_cents AS total_cents,
            p.is_active
        FROM {SALES_TABLE} s
        JOIN {PRODUCTS_TABLE} p ON p.product_id = s.product_id
        WHERE {where_sql}
        ORDER BY s.sale_date DESC, s.sale_id DESC
        """
    )
    with get_engine().connect() as connection:
        return pd.read_sql_query(sql, connection, params=params)


def load_categories() -> list[str]:
    sql = text(f"SELECT DISTINCT category_name FROM {PRODUCTS_TABLE} ORDER BY category_name")
    with get_engine().connect() as connection:
        categories_df = pd.read_sql_query(sql, connection)
    categories = categories_df["category_name"].astype(str).tolist()
    return ["All", *categories]


def main() -> None:
    st.set_page_config(page_title="02 Filters", layout="wide")
    st.title("02 Filters")
    st.caption("Sidebar filters with st.selectbox, st.slider, and dynamic WHERE clause building.")

    setup_schema(seed_only=True)
    if st.button("Reset Demo Data"):
        setup_schema(seed_only=False)
        st.success("Demo tables recreated and reseeded.")

    categories = load_categories()
    selected_category = st.sidebar.selectbox("Category", categories, index=0)
    min_price, max_price = st.sidebar.slider("Unit price range (USD)", 0, 1500, (0, 500))

    df = fetch_filtered(selected_category, min_price * 100, max_price * 100)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"Rows after filters: {len(df)}")


if __name__ == "__main__":
    main()
