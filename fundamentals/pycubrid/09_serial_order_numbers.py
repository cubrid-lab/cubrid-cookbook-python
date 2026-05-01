"""09_serial_order_numbers.py - Business order IDs with SERIAL.

Demonstrates:
- Creating and using SERIAL for business order numbers
- Inserting order headers and line items in one transaction
- Listing generated order numbers and totals
"""

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

import pycubrid
from datetime import datetime


DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_order_lines")
    cursor.execute("DROP TABLE IF EXISTS cookbook_orders")
    try:
        cursor.execute("DROP SERIAL cookbook_order_seq")
    except Exception:
        pass

    cursor.execute("CREATE SERIAL cookbook_order_seq START WITH 1000 INCREMENT BY 1")
    cursor.execute(
        """
        CREATE TABLE cookbook_orders (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            order_no       INT NOT NULL UNIQUE,
            customer_name  VARCHAR(120) NOT NULL,
            created_at_utc DATETIME NOT NULL,
            total_cents    INT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE cookbook_order_lines (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            order_no         INT NOT NULL,
            product_name     VARCHAR(120) NOT NULL,
            qty              INT NOT NULL,
            unit_price_cents INT NOT NULL,
            line_total_cents INT NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created serial 'cookbook_order_seq' and order tables")


def next_order_number(cursor):
    cursor.execute("SELECT cookbook_order_seq.NEXT_VALUE")
    row = cursor.fetchone()
    return row[0]


def create_order(cursor, customer, lines):
    order_no = next_order_number(cursor)
    created_at_utc = datetime.utcnow()
    total_cents = 0
    line_rows = []
    for product_name, qty, unit_price_cents in lines:
        line_total_cents = qty * unit_price_cents
        total_cents += line_total_cents
        line_rows.append((order_no, product_name, qty, unit_price_cents, line_total_cents))

    cursor.execute(
        """
        INSERT INTO cookbook_orders (order_no, customer_name, created_at_utc, total_cents)
        VALUES (?, ?, ?, ?)
        """,
        (order_no, customer, created_at_utc, total_cents),
    )
    cursor.executemany(
        """
        INSERT INTO cookbook_order_lines
            (order_no, product_name, qty, unit_price_cents, line_total_cents)
        VALUES (?, ?, ?, ?, ?)
        """,
        line_rows,
    )
    print(
        f"✓ Created order_no={order_no} customer={customer} "
        f"lines={len(line_rows)} total_cents={total_cents}"
    )


def list_orders(cursor):
    cursor.execute(
        """
        SELECT order_no, customer_name, created_at_utc, total_cents
          FROM cookbook_orders
         ORDER BY order_no
        """
    )
    orders = cursor.fetchall()
    print(f"\nOrders ({len(orders)} rows):")
    for order in orders:
        print(
            f"  order_no={order[0]} customer={order[1]} "
            f"created_at_utc={order[2]} total_cents={order[3]}"
        )
        cursor.execute(
            """
            SELECT product_name, qty, unit_price_cents, line_total_cents
              FROM cookbook_order_lines
             WHERE order_no = ?
             ORDER BY id
            """,
            (order[0],),
        )
        for line in cursor.fetchall():
            print(
                f"    - product={line[0]} qty={line[1]} "
                f"unit_price_cents={line[2]} line_total_cents={line[3]}"
            )


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_order_lines")
    cursor.execute("DROP TABLE IF EXISTS cookbook_orders")
    try:
        cursor.execute("DROP SERIAL cookbook_order_seq")
    except Exception:
        pass
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up order tables and serial 'cookbook_order_seq'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()

        create_order(
            cursor,
            "Alice",
            [
                ("Keyboard", 1, 4999),
                ("Mouse", 2, 2599),
            ],
        )
        create_order(
            cursor,
            "Bob",
            [
                ("Monitor", 1, 18999),
                ("HDMI Cable", 3, 1299),
            ],
        )
        conn.commit()
        list_orders(cursor)

        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
