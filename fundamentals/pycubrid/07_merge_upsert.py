"""07_merge_upsert.py - Idempotent reference sync with MERGE.

Demonstrates:
- Loading a latest external snapshot into a staging table
- MERGE INTO target USING staging (upsert by business key)
- Deactivating rows missing from the latest snapshot

If MERGE syntax fails on a specific server patch level, adapt to
INSERT ... ON DUPLICATE KEY UPDATE while keeping the same behavior.
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
    cursor.execute("DROP TABLE IF EXISTS cookbook_product_stage")
    cursor.execute("DROP TABLE IF EXISTS cookbook_products")

    cursor.execute(
        """
        CREATE TABLE cookbook_products (
            sku            VARCHAR(40) PRIMARY KEY,
            name           VARCHAR(200) NOT NULL,
            price_cents    INT NOT NULL,
            active         INT NOT NULL DEFAULT 1,
            last_seen_utc  DATETIME
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE cookbook_product_stage (
            sku         VARCHAR(40) PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            price_cents INT NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created tables 'cookbook_products' and 'cookbook_product_stage'")


def load_snapshot(cursor, rows):
    cursor.execute("DELETE FROM cookbook_product_stage")
    cursor.executemany(
        "INSERT INTO cookbook_product_stage (sku, name, price_cents) VALUES (?, ?, ?)",
        rows,
    )
    print(f"✓ Loaded snapshot rows into staging: {len(rows)}")


def merge_snapshot(cursor):
    now_utc = datetime.utcnow()
    cursor.execute(
        """
        MERGE INTO cookbook_products p
        USING cookbook_product_stage s
        ON (p.sku = s.sku)
        WHEN MATCHED THEN
            UPDATE SET
                p.name = s.name,
                p.price_cents = s.price_cents,
                p.active = 1,
                p.last_seen_utc = ?
        WHEN NOT MATCHED THEN
            INSERT (sku, name, price_cents, active, last_seen_utc)
            VALUES (s.sku, s.name, s.price_cents, 1, ?)
        """,
        (now_utc, now_utc),
    )
    print("✓ Merged staging snapshot into target table")


def deactivate_missing(cursor):
    cursor.execute(
        """
        UPDATE cookbook_products p
           SET p.active = 0
         WHERE NOT EXISTS (
               SELECT 1
                 FROM cookbook_product_stage s
                WHERE s.sku = p.sku
         )
        """
    )
    print(f"✓ Marked missing products inactive (rows affected: {cursor.rowcount})")


def show_results(cursor, label):
    cursor.execute(
        """
        SELECT sku, name, price_cents, active, last_seen_utc
          FROM cookbook_products
         ORDER BY sku
        """
    )
    rows = cursor.fetchall()
    print(f"\n{label} ({len(rows)} rows):")
    for row in rows:
        print(
            f"  sku={row[0]:8s} name={row[1]:18s} "
            f"price_cents={row[2]:6d} active={row[3]} last_seen_utc={row[4]}"
        )


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_product_stage")
    cursor.execute("DROP TABLE IF EXISTS cookbook_products")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up 'cookbook_product_stage' and 'cookbook_products'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_schema(conn)
        cursor = conn.cursor()

        seed_rows = [
            ("SKU-100", "Keyboard", 4999),
            ("SKU-200", "Mouse", 2599),
            ("SKU-300", "Monitor", 19999),
        ]
        load_snapshot(cursor, seed_rows)
        merge_snapshot(cursor)
        deactivate_missing(cursor)
        conn.commit()
        show_results(cursor, "After first snapshot")

        next_rows = [
            ("SKU-100", "Keyboard Pro", 6999),
            ("SKU-300", "Monitor", 18999),
            ("SKU-400", "Dock", 7999),
        ]
        print("\nApplying second snapshot...")
        load_snapshot(cursor, next_rows)
        merge_snapshot(cursor)
        deactivate_missing(cursor)
        conn.commit()
        show_results(cursor, "After second snapshot")

        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
