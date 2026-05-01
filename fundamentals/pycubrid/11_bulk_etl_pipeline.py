"""11_bulk_etl_pipeline.py — Chunked ETL with staging table.

Demonstrates:
- Generating source rows
- Chunked staging inserts with executemany()
- Validation and rejection workflow
- Deduplication and apply to final table
- ETL summary metrics and cleanup

Adaptation note:
- To keep behavior predictable on CUBRID 11.2, apply-stage upsert uses
  SELECT-then-INSERT/UPDATE logic instead of relying on a dialect-specific
  UPSERT form.
"""

from __future__ import annotations

import datetime
import pycubrid  # type: ignore[import-not-found]

CONNECT = getattr(pycubrid, "connect")

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection():
    return CONNECT(**DB_CONFIG)


def setup_schema(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales_stage")
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales")
    cursor.execute("""
        CREATE TABLE cookbook_sales_stage (
            stage_id     INT AUTO_INCREMENT PRIMARY KEY,
            source_row   INT NOT NULL,
            order_no     VARCHAR(40),
            customer_id  VARCHAR(40),
            sold_at      DATETIME,
            amount_cents INT,
            is_valid     INT DEFAULT 0,
            reject_reason VARCHAR(120)
        )
    """)
    cursor.execute("""
        CREATE TABLE cookbook_sales (
            order_no      VARCHAR(40) PRIMARY KEY,
            customer_id   VARCHAR(40) NOT NULL,
            sold_at       DATETIME NOT NULL,
            amount_cents  INT NOT NULL,
            updated_at    DATETIME NOT NULL
        )
    """)
    conn.commit()
    cursor.close()
    print("✓ Created tables 'cookbook_sales_stage' and 'cookbook_sales'")


def generate_source_rows(n: int = 1000) -> list[tuple[int, str, str, datetime.datetime, int]]:
    rows = []
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    for i in range(1, n + 1):
        order_no = f"ORD-{((i - 1) % 930) + 1:05d}"
        customer_id = f"CUST-{((i - 1) % 120) + 1:04d}"
        sold_at = now - datetime.timedelta(minutes=i)
        amount_cents = 1000 + (i % 250) * 15

        if i % 25 == 0:
            amount_cents = -1
        if i % 40 == 0:
            order_no = ""
        if i % 60 == 0:
            customer_id = ""

        rows.append((i, order_no, customer_id, sold_at, amount_cents))
    return rows


def load_stage_in_chunks(
    cursor,
    rows: list[tuple[int, str, str, datetime.datetime, int]],
    chunk_size: int = 100,
) -> int:
    loaded = 0
    sql = """
        INSERT INTO cookbook_sales_stage (
            source_row, order_no, customer_id, sold_at, amount_cents
        ) VALUES (?, ?, ?, ?, ?)
    """
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        cursor.executemany(sql, chunk)
        loaded += len(chunk)
        print(f"  ✓ Staged chunk {i // chunk_size + 1}: {len(chunk)} rows")
    return loaded


def validate_stage(cursor) -> tuple[int, int]:
    cursor.execute("UPDATE cookbook_sales_stage SET is_valid = 0, reject_reason = NULL")
    cursor.execute("""
        UPDATE cookbook_sales_stage
        SET reject_reason = 'missing order_no'
        WHERE order_no IS NULL OR order_no = ''
    """)
    cursor.execute("""
        UPDATE cookbook_sales_stage
        SET reject_reason = 'missing customer_id'
        WHERE reject_reason IS NULL AND (customer_id IS NULL OR customer_id = '')
    """)
    cursor.execute("""
        UPDATE cookbook_sales_stage
        SET reject_reason = 'invalid amount'
        WHERE reject_reason IS NULL AND (amount_cents IS NULL OR amount_cents <= 0)
    """)
    cursor.execute("""
        UPDATE cookbook_sales_stage
        SET reject_reason = 'missing sold_at'
        WHERE reject_reason IS NULL AND sold_at IS NULL
    """)
    cursor.execute("""
        UPDATE cookbook_sales_stage
        SET is_valid = 1
        WHERE reject_reason IS NULL
    """)

    cursor.execute("SELECT COUNT(*) FROM cookbook_sales_stage WHERE is_valid = 1")
    validated = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_sales_stage WHERE is_valid = 0")
    rejected = cursor.fetchone()[0]
    print(f"✓ Validation complete: valid={validated}, rejected={rejected}")
    return validated, rejected


def apply_stage(cursor) -> tuple[int, int]:
    inserted = 0
    updated = 0
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    cursor.execute("""
        SELECT s.order_no, s.customer_id, s.sold_at, s.amount_cents
        FROM cookbook_sales_stage s
        JOIN (
            SELECT order_no, MAX(stage_id) AS max_stage_id
            FROM cookbook_sales_stage
            WHERE is_valid = 1
            GROUP BY order_no
        ) latest ON latest.order_no = s.order_no AND latest.max_stage_id = s.stage_id
        ORDER BY s.stage_id
    """)
    rows = cursor.fetchall()

    for order_no, customer_id, sold_at, amount_cents in rows:
        cursor.execute("SELECT COUNT(*) FROM cookbook_sales WHERE order_no = ?", (order_no,))
        exists = cursor.fetchone()[0] > 0
        if exists:
            cursor.execute(
                """
                UPDATE cookbook_sales
                SET customer_id = ?, sold_at = ?, amount_cents = ?, updated_at = ?
                WHERE order_no = ?
                """,
                (customer_id, sold_at, amount_cents, now, order_no),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO cookbook_sales (
                    order_no, customer_id, sold_at, amount_cents, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (order_no, customer_id, sold_at, amount_cents, now),
            )
            inserted += 1

    print(f"✓ Applied staged rows into target: inserted={inserted}, updated={updated}")
    return inserted, updated


def print_summary(cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM cookbook_sales_stage")
    loaded = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_sales_stage WHERE is_valid = 1")
    validated = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_sales_stage WHERE is_valid = 0")
    rejected = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_sales")
    target = cursor.fetchone()[0]

    print("\n=== ETL Summary ===")
    print(f"  Loaded:    {loaded}")
    print(f"  Validated: {validated}")
    print(f"  Rejected:  {rejected}")
    print(f"  Target rows after apply: {target}")

    cursor.execute("""
        SELECT stage_id, source_row, order_no, customer_id, amount_cents, reject_reason
        FROM cookbook_sales_stage
        WHERE is_valid = 0
        ORDER BY stage_id
    """)
    bad_rows = cursor.fetchmany(5)
    print("\nRejected examples (first 5):")
    if not bad_rows:
        print("  (none)")
    else:
        for row in bad_rows:
            print(
                f"  stage_id={row[0]} source_row={row[1]} "
                f"order_no='{row[2]}' customer_id='{row[3]}' "
                f"amount_cents={row[4]} reason='{row[5]}'"
            )

    cursor.execute("""
        SELECT order_no, customer_id, amount_cents
        FROM cookbook_sales
        ORDER BY order_no
    """)
    top_rows = cursor.fetchmany(5)
    print("\nTarget sample (first 5 by order_no):")
    for row in top_rows:
        print(f"  {row[0]}  customer={row[1]}  amount_cents={row[2]}")


def cleanup(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales_stage")
    cursor.execute("DROP TABLE IF EXISTS cookbook_sales")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up ETL tables")


if __name__ == "__main__":
    conn = get_connection()
    loaded_count = 0
    validated_count = 0
    rejected_count = 0
    inserted_count = 0
    updated_count = 0

    try:
        setup_schema(conn)
        source_rows = generate_source_rows(1000)
        print(f"Generated source rows: {len(source_rows)}")

        cursor = conn.cursor()
        loaded_count = load_stage_in_chunks(cursor, source_rows, chunk_size=100)
        validated_count, rejected_count = validate_stage(cursor)
        inserted_count, updated_count = apply_stage(cursor)
        conn.commit()

        print_summary(cursor)
        cursor.close()

        print("\n=== Final Counts ===")
        print(
            f"  loaded={loaded_count}, validated={validated_count}, rejected={rejected_count}, "
            f"inserted={inserted_count}, updated={updated_count}"
        )
    finally:
        cleanup(conn)
        conn.close()
