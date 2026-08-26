"""20_timezone_datetime.py - Timezone-aware datetime types.

Demonstrates:
- SET TIME ZONE to pin the session zone (makes *LTZ values deterministic)
- DATETIMETZ: stores an explicit zone, read back as a tz-aware datetime
- DATETIMELTZ: stored in UTC; pycubrid materializes native reads as UTC-aware
  (+00:00) datetimes. Server-side formatting (TO_CHAR) is the path for rendering
  in the pinned session zone.
- Server-side TO_CHAR rendering with the TZR (zone-region) format element

Note on TIMESTAMPTZ / TIMESTAMPLTZ:
    Reading those two column types natively currently triggers a pycubrid
    parsing bug (cubrid-lab/pycubrid#289), so this recipe reads TIMESTAMPTZ
    only via server-side TO_CHAR(), which is unaffected. DATETIMETZ and
    DATETIMELTZ read back natively without issue.
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

SESSION_TZ = "Asia/Seoul"


def get_connection():
    return pycubrid.connect(**DB_CONFIG)


def pin_session_zone(cursor):
    # Session-scoped: makes DATETIMELTZ rendering independent of the server's OS zone.
    cursor.execute(f"SET TIME ZONE '{SESSION_TZ}'")
    print(f"✓ Session time zone pinned to '{SESSION_TZ}'")


def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_events")
    cursor.execute(
        """
        CREATE TABLE cookbook_events (
            id      INT PRIMARY KEY,
            label   VARCHAR(30) NOT NULL,
            at_tz   DATETIMETZ NOT NULL,
            at_ltz  DATETIMELTZ NOT NULL,
            at_ts   TIMESTAMPTZ NOT NULL
        )
        """
    )
    conn.commit()
    cursor.close()
    print("✓ Created table 'cookbook_events'")


def seed_events(cursor):
    cursor.execute(
        """
        INSERT INTO cookbook_events (id, label, at_tz, at_ltz, at_ts) VALUES
            (1, 'seoul-launch',
             DATETIMETZ '2026-01-15 10:30:00 Asia/Seoul',
             DATETIMELTZ '2026-01-15 10:30:00',
             TIMESTAMPTZ '2026-01-15 10:30:00 Asia/Seoul'),
            (2, 'utc-batch',
             DATETIMETZ '2026-01-15 10:30:00 UTC',
             DATETIMELTZ '2026-01-15 01:30:00',
             TIMESTAMPTZ '2026-01-15 10:30:00 UTC')
        """
    )
    print("✓ Inserted events: 2")


def read_native(cursor):
    # DATETIMETZ keeps its explicit zone; DATETIMELTZ comes back UTC-aware (+00:00)
    # from the driver, not in the session zone. Use TO_CHAR server-side for that.
    cursor.execute("SELECT id, label, at_tz, at_ltz FROM cookbook_events ORDER BY id")
    print("\nNative tz-aware datetimes (DATETIMETZ, DATETIMELTZ):")
    for event_id, label, at_tz, at_ltz in cursor.fetchall():
        tz_str = at_tz.isoformat(sep=" ", timespec="seconds")
        ltz_str = at_ltz.isoformat(sep=" ", timespec="seconds")
        print(f"  id={event_id} {label:<12} tz={tz_str}  ltz={ltz_str}")


def read_via_to_char(cursor):
    # TIMESTAMPTZ rendered server-side to sidestep pycubrid#289.
    cursor.execute(
        """
        SELECT id, label,
               TO_CHAR(at_ts, 'YYYY-MM-DD HH24:MI:SS TZR')
          FROM cookbook_events
         ORDER BY id
        """
    )
    print("\nTIMESTAMPTZ via server-side TO_CHAR (zone region):")
    for event_id, label, rendered in cursor.fetchall():
        print(f"  id={event_id} {label:<12} ts={rendered}")


def cleanup(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_events")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up table 'cookbook_events'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        cursor = conn.cursor()
        pin_session_zone(cursor)
        cursor.close()

        setup_schema(conn)
        cursor = conn.cursor()
        pin_session_zone(cursor)
        seed_events(cursor)
        conn.commit()
        read_native(cursor)
        read_via_to_char(cursor)
        cursor.close()
    finally:
        cleanup(conn)
        conn.close()
