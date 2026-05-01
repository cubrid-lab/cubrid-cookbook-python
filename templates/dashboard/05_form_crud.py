"""Streamlit recipe: create, update, and delete rows using st.form and SQL DML."""

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


def bootstrap(reset: bool = False) -> None:
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

        product_count = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}")).scalar_one()
        )
        if product_count == 0:
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

        sales_count = int(
            connection.execute(text(f"SELECT COUNT(*) FROM {SALES_TABLE}")).scalar_one()
        )
        if sales_count == 0:
            start = date(2026, 1, 1)
            rows = [
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
                rows,
            )


def list_products() -> pd.DataFrame:
    with get_engine().connect() as connection:
        return pd.read_sql_query(
            text(
                f"""
                SELECT product_id, product_name, category_name, unit_price_cents, is_active
                FROM {PRODUCTS_TABLE}
                ORDER BY product_id
                """
            ),
            connection,
        )


def add_product(
    product_name: str, category_name: str, unit_price_cents: int, is_active: int
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                f"""
                INSERT INTO {PRODUCTS_TABLE} (product_name, category_name, unit_price_cents, is_active)
                VALUES (:product_name, :category_name, :unit_price_cents, :is_active)
                """
            ),
            {
                "product_name": product_name,
                "category_name": category_name,
                "unit_price_cents": unit_price_cents,
                "is_active": is_active,
            },
        )


def update_product(product_id: int, unit_price_cents: int, is_active: int) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                f"""
                UPDATE {PRODUCTS_TABLE}
                SET unit_price_cents = :unit_price_cents, is_active = :is_active
                WHERE product_id = :product_id
                """
            ),
            {
                "product_id": product_id,
                "unit_price_cents": unit_price_cents,
                "is_active": is_active,
            },
        )


def delete_product(product_id: int) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(f"DELETE FROM {SALES_TABLE} WHERE product_id = :product_id"),
            {"product_id": product_id},
        )
        connection.execute(
            text(f"DELETE FROM {PRODUCTS_TABLE} WHERE product_id = :product_id"),
            {"product_id": product_id},
        )


def main() -> None:
    st.set_page_config(page_title="05 Form CRUD", layout="wide")
    st.title("05 Form CRUD")
    st.caption("Create, update, and delete rows through st.form submit actions.")

    bootstrap(reset=False)
    if st.button("Reset Demo Data"):
        bootstrap(reset=True)
        st.success("Demo tables recreated and reseeded.")

    st.subheader("Current Products")
    products_df = list_products()
    st.dataframe(products_df, use_container_width=True, hide_index=True)

    with st.form("add_form"):
        st.markdown("**Add Product**")
        add_name = st.text_input("Product name", value="")
        add_category = st.selectbox("Category", ["Electronics", "Home", "Office", "Lifestyle"])
        add_price_dollars = st.number_input("Price (USD)", min_value=0, value=99, step=1)
        add_active = st.selectbox("Active", [1, 0], index=0)
        add_submit = st.form_submit_button("Insert")
        if add_submit and add_name.strip():
            add_product(
                add_name.strip(), add_category, int(add_price_dollars) * 100, int(add_active)
            )
            st.success("Inserted.")
            st.rerun()

    with st.form("edit_form"):
        st.markdown("**Edit Product**")
        product_ids = products_df["product_id"].astype(int).tolist()
        if product_ids:
            selected_id = st.selectbox("Product ID", product_ids)
            edit_price_dollars = st.number_input("New price (USD)", min_value=0, value=100, step=1)
            edit_active = st.selectbox("New active", [1, 0], index=0)
            edit_submit = st.form_submit_button("Update")
            if edit_submit:
                update_product(int(selected_id), int(edit_price_dollars) * 100, int(edit_active))
                st.success("Updated.")
                st.rerun()
        else:
            st.info("No products available to edit.")

    with st.form("delete_form"):
        st.markdown("**Delete Product**")
        product_ids = products_df["product_id"].astype(int).tolist()
        if product_ids:
            delete_id = st.selectbox("Delete Product ID", product_ids)
            delete_submit = st.form_submit_button("Delete")
            if delete_submit:
                delete_product(int(delete_id))
                st.success("Deleted.")
                st.rerun()
        else:
            st.info("No products available to delete.")


if __name__ == "__main__":
    main()
