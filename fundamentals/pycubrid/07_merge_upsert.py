"""07_merge_upsert.py - Idempotent reference sync with MERGE.

Demonstrates:
- Loading a latest external snapshot into a staging table
- MERGE INTO target USING staging (upsert by business key)
- Deactivating rows missing from the latest snapshot

If MERGE syntax fails on a specific server patch level, adapt to
INSERT ... ON DUPLICATE KEY UPDATE while keeping the same behavior.

Data safety (#627): the lesson refuses to run when either table already
exists (dropping them could destroy someone else's data), and tracks which
tables each run actually created, so a partial setup failure or a failed
cleanup only ever drops this run's own tables. The original error is kept
when cleanup fails too.
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportMissingImports=false

import sys

import pycubrid
from datetime import datetime, timezone


TARGET_TABLE = "cookbook_merge_products"
STAGE_TABLE = "cookbook_product_stage"


DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def table_exists(cursor, name):
    """Read-only existence probe: a SELECT against the table fails iff it is missing.

    A catalog query would work too, but this probe needs no catalog knowledge
    and never reads the table's rows. `name` is a module constant, not user input.
    """
    try:
        cursor.execute(f"SELECT 1 FROM {name} WHERE 1 = 0")
        return True
    except Exception:
        return False


def drop_owned(conn, names):
    """Drop exactly the tables this run created, newest first."""
    if not names:
        return
    cursor = conn.cursor()
    try:
        for name in reversed(names):
            cursor.execute(f"DROP TABLE IF EXISTS {name}")
        conn.commit()
    finally:
        cursor.close()


def setup_schema(conn):
    """Create the target and staging tables, refusing to touch existing ones.

    Returns the list of tables this call created, so cleanup drops only those
    even when creation fails halfway (#627). A collision with pre-existing
    tables raises before any destructive SQL runs.
    """
    cursor = conn.cursor()
    existing = [n for n in (STAGE_TABLE, TARGET_TABLE) if table_exists(cursor, n)]
    cursor.close()
    if existing:
        raise RuntimeError(
            "refusing to run: "
            + ", ".join(f"'{n}'" for n in existing)
            + " already exist and this lesson would DROP them — "
            "drop them manually first, or run the lesson in a scratch database (#627)"
        )

    created = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE cookbook_merge_products (
                sku            VARCHAR(40) PRIMARY KEY,
                name           VARCHAR(200) NOT NULL,
                price_cents    INT NOT NULL,
                active         INT NOT NULL DEFAULT 1,
                last_seen_utc  DATETIME
            )
            """
        )
        created.append(TARGET_TABLE)
        cursor.execute(
            """
            CREATE TABLE cookbook_product_stage (
                sku         VARCHAR(40) PRIMARY KEY,
                name        VARCHAR(200) NOT NULL,
                price_cents INT NOT NULL
            )
            """
        )
        created.append(STAGE_TABLE)
        conn.commit()
        cursor.close()
    except Exception as original:
        # Clean up only what this run actually created; if that cleanup fails
        # too, the ORIGINAL error is the one that propagates (#627).
        try:
            drop_owned(conn, created)
        except Exception as cleanup_error:
            raise original from cleanup_error
        raise
    print("✓ Created tables 'cookbook_merge_products' and 'cookbook_product_stage'")
    return created


def load_snapshot(cursor, rows):
    cursor.execute("DELETE FROM cookbook_product_stage")
    cursor.executemany(
        "INSERT INTO cookbook_product_stage (sku, name, price_cents) VALUES (?, ?, ?)",
        rows,
    )
    print(f"✓ Loaded snapshot rows into staging: {len(rows)}")


def merge_snapshot(cursor):
    now_utc = datetime.now(timezone.utc)
    cursor.execute(
        """
        MERGE INTO cookbook_merge_products p
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
        UPDATE cookbook_merge_products p
           SET p.active = 0
         WHERE NOT EXISTS (
               SELECT 1
                 FROM cookbook_product_stage s
                WHERE s.sku = p.sku
         )
        """
    )
    print(f"✓ Marked missing products inactive (rows affected: {cursor.rowcount})")


def format_timestamp(value):
    """Render a DATETIME value with a fixed millisecond fractional part.

    CUBRID's DATETIME column has millisecond precision, but Python's
    ``datetime.__str__()`` omits the fractional part entirely when the
    microsecond component is exactly 0 -- i.e. whenever the stored value
    lands on a whole second, about 1 run in 1000 -- which made the golden
    comparison flaky (#189). Always printing the fractional part keeps the
    output format stable regardless of the sub-second value.
    """
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def show_results(cursor, label):
    cursor.execute(
        """
        SELECT sku, name, price_cents, active, last_seen_utc
          FROM cookbook_merge_products
         ORDER BY sku
        """
    )
    rows = cursor.fetchall()
    print(f"\n{label} ({len(rows)} rows):")
    for row in rows:
        print(
            f"  sku={row[0]:8s} name={row[1]:18s} "
            f"price_cents={row[2]:6d} active={row[3]} last_seen_utc={format_timestamp(row[4])}"
        )


def cleanup(conn, owned):
    """Drop only the tables this run created, tracking per-table failures.

    `owned` is the list returned by setup_schema; an empty list (refused or
    failed setup) drops nothing, so pre-existing tables are never touched.
    """
    if not owned:
        return
    cursor = conn.cursor()
    dropped = []
    failures = []
    try:
        for name in reversed(owned):
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {name}")
                dropped.append(name)
            except Exception as e:
                failures.append(f"{name}: {e}")
        conn.commit()
    finally:
        cursor.close()
    print("\n✓ Cleaned up 'cookbook_product_stage' and 'cookbook_merge_products'")
    if failures:
        raise RuntimeError(
            "cleanup failed for "
            + "; ".join(failures)
            + f" (dropped: {', '.join(dropped) if dropped else 'none'})"
        )


def main():
    conn = get_connection()
    owned = []

    try:
        owned = setup_schema(conn)
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
        try:
            cleanup(conn, owned)
        except Exception as cleanup_error:
            # Keep the original error when cleanup also fails (#627); only a
            # cleanup failure on an otherwise-successful run raises.
            if sys.exc_info()[0] is None:
                raise
            print(
                f"warning: cleanup failed ({cleanup_error}); the original error is kept",
                file=sys.stderr,
            )
        conn.close()


if __name__ == "__main__":
    main()
