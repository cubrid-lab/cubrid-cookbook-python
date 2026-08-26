"""17_window_functions.py - Analytic (window) functions.

Demonstrates:
- ROW_NUMBER() / RANK() / DENSE_RANK() ranking within partitions
- LAG() to compare a row with the previous row
- Running total with SUM() OVER (... ORDER BY ...)
- Deterministic tie-breakers on ROW_NUMBER/RANK; DENSE_RANK omits one on
  purpose to keep the West 300/300 tie visible
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

import pycubrid


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
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales")
    cursor.execute(
        """
        CREATE TABLE cookbook_sales (
            sale_id INT PRIMARY KEY,
            region  VARCHAR(20) NOT NULL,
            product VARCHAR(20) NOT NULL,
            amount  INT NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_sales'")


def seed_sales(cursor):
    rows = [
        (1, "East", "Widget", 100),
        (2, "East", "Gadget", 200),
        (3, "East", "Gizmo", 150),
        (4, "West", "Widget", 300),
        (5, "West", "Gadget", 50),
        (6, "West", "Gizmo", 300),
    ]
    cursor.executemany(
        "INSERT INTO cookbook_sales (sale_id, region, product, amount) VALUES (?, ?, ?, ?)",
        rows,
    )
    print(f"✓ Inserted sales rows: {len(rows)}")


def rank_within_region(cursor):
    # ROW_NUMBER and RANK add sale_id as a tie-breaker so results are stable.
    # DENSE_RANK deliberately omits it: the West 300/300 tie stays a genuine tie
    # (both rank 1), which is the point of the DENSE_RANK column here.
    cursor.execute(
        """
        SELECT region, product, amount,
               ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC, sale_id) AS rn,
               RANK()       OVER (PARTITION BY region ORDER BY amount DESC, sale_id) AS rnk,
               DENSE_RANK() OVER (PARTITION BY region ORDER BY amount DESC)          AS dense
          FROM cookbook_sales
         ORDER BY region, amount DESC, sale_id
        """
    )
    print("\nRanking within each region (by amount desc):")
    print("  region  product  amount  row_number  rank  dense_rank")
    for region, product, amount, rn, rnk, dense in cursor.fetchall():
        print(f"  {region:<6}  {product:<7}  {amount:>6}  {rn:>10}  {rnk:>4}  {dense:>10}")


def running_total_and_lag(cursor):
    cursor.execute(
        """
        SELECT region, product, amount,
               LAG(amount) OVER (PARTITION BY region ORDER BY amount DESC, sale_id) AS prev_amount,
               SUM(amount) OVER (PARTITION BY region ORDER BY amount DESC, sale_id) AS running_total
          FROM cookbook_sales
         ORDER BY region, amount DESC, sale_id
        """
    )
    print("\nLAG and running total within each region:")
    print("  region  product  amount  prev_amount  running_total")
    for region, product, amount, prev_amount, running in cursor.fetchall():
        prev_str = "(none)" if prev_amount is None else str(prev_amount)
        print(f"  {region:<6}  {product:<7}  {amount:>6}  {prev_str:>11}  {running:>13}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_sales'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()
        seed_sales(cursor)
        conn.commit()
        rank_within_region(cursor)
        running_total_and_lag(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
