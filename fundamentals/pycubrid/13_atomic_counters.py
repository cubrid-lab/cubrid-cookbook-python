"""13_atomic_counters.py — Atomic counters for hot-path metrics.

Demonstrates:
- Counter table keyed by metric_key + day
- Atomic increment with ON DUPLICATE KEY UPDATE
- Efficient batch event recording
- Top-N rankings query

Adaptation note:
- If ON DUPLICATE KEY UPDATE fails on your server build, switch to a
  SELECT-then-INSERT/UPDATE pattern. This script uses ODKU directly because it
  is supported on standard CUBRID 11.2 setups.
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
    cursor.execute("DROP TABLE IF EXISTS cookbook_counters")
    cursor.execute("""
        CREATE TABLE cookbook_counters (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            metric_key VARCHAR(120) NOT NULL,
            metric_day DATE NOT NULL,
            hit_count  INT NOT NULL DEFAULT 0,
            UNIQUE (metric_key, metric_day)
        )
    """)
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_counters'")


def record_event(
    cursor,
    key: str,
    day: datetime.date,
    delta: int = 1,
) -> None:
    cursor.execute(
        """
        INSERT INTO cookbook_counters (metric_key, metric_day, hit_count)
        VALUES (?, ?, ?)
        ON DUPLICATE KEY UPDATE hit_count = hit_count + ?
        """,
        (key, day, delta, delta),
    )


def record_batch(
    cursor,
    events: list[tuple[str, datetime.date, int]],
) -> None:
    for key, day, delta in events:
        record_event(cursor, key, day, delta)


def show_rankings(cursor) -> None:
    print("\n=== Top Metrics (today) ===")
    today = datetime.datetime.now(datetime.timezone.utc).date()
    cursor.execute(
        """
        SELECT metric_key, hit_count
        FROM cookbook_counters
        WHERE metric_day = ?
        ORDER BY hit_count DESC, metric_key ASC
        LIMIT 5
        """,
        (today,),
    )
    rows = cursor.fetchall()
    for i, row in enumerate(rows, start=1):
        print(f"  {i}. {row[0]:28s} {row[1]}")

    print("\n=== Before/After State ===")
    cursor.execute(
        "SELECT metric_key, hit_count FROM cookbook_counters WHERE metric_day = ? ORDER BY metric_key",
        (today,),
    )
    rows = cursor.fetchall()
    for row in rows:
        print(f"  {row[0]:28s} count={row[1]}")


def cleanup(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_counters")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_counters'")


if __name__ == "__main__":
    conn = get_connection()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    yesterday = today - datetime.timedelta(days=1)

    try:
        setup_schema(conn)
        cursor = conn.cursor()

        print("=== Recording single events ===")
        record_event(cursor, "page.home.view", today, 1)
        record_event(cursor, "page.home.view", today, 1)
        record_event(cursor, "api.login.success", today, 1)
        record_event(cursor, "api.login.success", today, 2)
        record_event(cursor, "api.login.failure", today, 1)

        print("✓ Recorded initial events")

        print("\n=== Recording batch events ===")
        batch_events = [
            ("page.home.view", today, 6),
            ("page.product.view", today, 4),
            ("page.checkout.view", today, 2),
            ("api.login.success", today, 3),
            ("api.orders.create", today, 5),
            ("api.orders.create", today, 7),
            ("api.orders.cancel", today, 1),
            ("api.orders.create", yesterday, 9),
        ]
        record_batch(cursor, batch_events)
        conn.commit()
        print(f"✓ Recorded batch of {len(batch_events)} events")

        show_rankings(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
