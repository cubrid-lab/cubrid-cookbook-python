"""20_timezone_datetime.py - Timezone-aware datetime types.

Demonstrates:
- SET TIME ZONE to pin the session zone (makes *LTZ values deterministic)
- DATETIMETZ: stores an explicit zone, read back as a tz-aware datetime
- DATETIMELTZ: stored as an absolute instant; the server returns it in the
  session time zone, so native reads come back aware in the pinned zone
  (+09:00 here). The same instant reads as +00:00 in a UTC session.
- TIMESTAMPTZ: second precision with an explicit zone, read back natively as a
  tz-aware datetime (pycubrid >= 1.7.0 fixed these reads, cubrid-lab/pycubrid#289)
- The session zone survives commit() on pycubrid >= 1.8.0 (#468/#472). On
  1.7.x a commit silently reconnected and dropped it, so reads after a commit
  fell back to the server default zone (UTC in the cubrid/cubrid images).
- Server-side TO_CHAR rendering with the TZR (zone-region) format element
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
    # Re-applying it after a commit is only needed on pycubrid < 1.8.0.
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
    # DATETIMETZ and TIMESTAMPTZ keep their explicit zone; DATETIMELTZ comes back
    # aware in the session zone (Asia/Seoul, +09:00), still the same instant as stored.
    cursor.execute("SELECT id, label, at_tz, at_ltz, at_ts FROM cookbook_events ORDER BY id")
    print("\nNative tz-aware datetimes (DATETIMETZ, DATETIMELTZ, TIMESTAMPTZ):")
    for event_id, label, at_tz, at_ltz, at_ts in cursor.fetchall():
        tz_str = at_tz.isoformat(sep=" ", timespec="seconds")
        ltz_str = at_ltz.isoformat(sep=" ", timespec="seconds")
        ts_str = at_ts.isoformat(sep=" ", timespec="seconds")
        print(f"  id={event_id} {label:<12} tz={tz_str}  ltz={ltz_str}  ts={ts_str}")


def read_via_to_char(cursor):
    # isoformat() above prints only the UTC offset; TO_CHAR's TZR element renders
    # the zone's region name on the server instead.
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
