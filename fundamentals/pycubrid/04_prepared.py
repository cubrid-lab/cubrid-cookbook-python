"""04_prepared.py — Parameterized queries and batch operations.

Demonstrates:
- Parameterized queries (qmark style: ?)
- Preventing SQL injection
- executemany for batch inserts
- Batch operations with executemany
"""

from __future__ import annotations

import time

import pycubrid

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection() -> pycubrid.Connection:
    return pycubrid.connect(**DB_CONFIG)


def setup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_products")
    cursor.execute("""
        CREATE TABLE cookbook_products (
            id       INT AUTO_INCREMENT PRIMARY KEY,
            name     VARCHAR(200) NOT NULL,
            category VARCHAR(100),
            price    DOUBLE DEFAULT 0.0,
            stock    INT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()


def parameterized_queries(conn: pycubrid.Connection) -> None:
    """Use ? placeholders for safe parameterized queries."""
    print("=== Parameterized Queries ===")
    cursor = conn.cursor()

    # pycubrid uses qmark paramstyle: ?
    cursor.execute(
        "INSERT INTO cookbook_products (name, category, price, stock) VALUES (?, ?, ?, ?)",
        ("Laptop", "Electronics", 999.99, 50),
    )
    cursor.execute(
        "INSERT INTO cookbook_products (name, category, price, stock) VALUES (?, ?, ?, ?)",
        ("Mouse", "Electronics", 29.99, 200),
    )
    cursor.execute(
        "INSERT INTO cookbook_products (name, category, price, stock) VALUES (?, ?, ?, ?)",
        ("Desk Chair", "Furniture", 399.00, 30),
    )
    conn.commit()
    print("  ✓ Inserted 3 products with parameterized queries")

    # SELECT with parameters
    cursor.execute(
        "SELECT name, price FROM cookbook_products WHERE category = ? AND price > ?",
        ("Electronics", 50.0),
    )
    rows = cursor.fetchall()
    print(f"  Electronics > $50: {[(r[0], r[1]) for r in rows]}")

    cursor.close()


def sql_injection_safe(conn: pycubrid.Connection) -> None:
    """Demonstrate SQL injection safety with parameterized queries."""
    print("\n=== SQL Injection Safety ===")
    cursor = conn.cursor()

    # DANGEROUS (never do this!):
    # user_input = "'; DROP TABLE cookbook_products; --"
    # cursor.execute(f"SELECT * FROM cookbook_products WHERE name = '{user_input}'")

    # SAFE — parameters are escaped automatically:
    malicious_input = "'; DROP TABLE cookbook_products; --"
    cursor.execute(
        "SELECT name, price FROM cookbook_products WHERE name = ?",
        (malicious_input,),
    )
    rows = cursor.fetchall()
    print(f"  Malicious input returned {len(rows)} rows (table is safe!)")

    # Verify table still exists
    cursor.execute("SELECT COUNT(*) FROM cookbook_products")
    count = cursor.fetchone()[0]
    print(f"  ✓ Table still has {count} rows — SQL injection prevented")

    cursor.close()


def batch_insert(conn: pycubrid.Connection) -> None:
    """executemany — efficient batch inserts."""
    print("\n=== Batch Insert (executemany) ===")
    cursor = conn.cursor()

    products = [
        ("Keyboard", "Electronics", 79.99, 150),
        ("Monitor", "Electronics", 349.99, 40),
        ("Standing Desk", "Furniture", 599.00, 20),
        ("Headphones", "Electronics", 149.99, 100),
        ("Webcam", "Electronics", 89.99, 75),
        ("Bookshelf", "Furniture", 199.00, 25),
        ("USB Hub", "Electronics", 39.99, 300),
        ("Desk Lamp", "Furniture", 49.99, 60),
    ]

    start = time.perf_counter()
    cursor.executemany(
        "INSERT INTO cookbook_products (name, category, price, stock) VALUES (?, ?, ?, ?)",
        products,
    )
    conn.commit()
    elapsed = time.perf_counter() - start

    print(f"  ✓ Inserted {len(products)} products in {elapsed * 1000:.1f}ms")

    # Verify
    cursor.execute("SELECT COUNT(*) FROM cookbook_products")
    total = cursor.fetchone()[0]
    print(f"  Total products: {total}")

    cursor.close()


def batch_update(conn: pycubrid.Connection) -> None:
    """Batch updates with executemany."""
    print("\n=== Batch Update ===")
    cursor = conn.cursor()

    # Apply 10% discount to specific products
    updates = [
        (0.9, "Laptop"),
        (0.9, "Monitor"),
        (0.9, "Standing Desk"),
    ]

    cursor.executemany(
        "UPDATE cookbook_products SET price = price * ? WHERE name = ?",
        updates,
    )
    conn.commit()
    print(f"  ✓ Applied 10% discount to {len(updates)} products")

    # Show discounted prices
    cursor.execute(
        "SELECT name, price FROM cookbook_products WHERE name IN ('Laptop', 'Monitor', 'Standing Desk')"
    )
    for row in cursor.fetchall():
        print(f"  {row[0]:15s} → ${row[1]:.2f}")

    cursor.close()


def aggregate_queries(conn: pycubrid.Connection) -> None:
    """Aggregation with GROUP BY."""
    print("\n=== Aggregate Queries ===")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT category,
               COUNT(*) AS cnt,
               CAST(AVG(price) AS DOUBLE) AS avg_price,
               CAST(SUM(stock) AS INT) AS total_stock
        FROM cookbook_products
        GROUP BY category
        ORDER BY cnt DESC
    """)

    print(f"  {'Category':15s}  {'Count':>5s}  {'Avg Price':>10s}  {'Stock':>6s}")
    print(f"  {'--------':15s}  {'-----':>5s}  {'---------':>10s}  {'-----':>6s}")
    for row in cursor.fetchall():
        print(f"  {row[0]:15s}  {row[1]:5d}  ${row[2]:9.2f}  {row[3]:6d}")

    cursor.close()


def cleanup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_products")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup(conn)
        parameterized_queries(conn)
        sql_injection_safe(conn)
        batch_insert(conn)
        batch_update(conn)
        aggregate_queries(conn)
    finally:
        cleanup(conn)
        conn.close()
