"""22_date_formatting.py - Formatting and parsing dates with TO_CHAR / TO_DATE.

Demonstrates:
- TO_CHAR(date, fmt) to render dates and datetimes in several layouts
- TO_DATE(str, fmt) to parse strings in one layout, then re-render in another
- TO_CHAR(number, fmt) for grouped/padded numeric formatting
- How fixed-width format elements pad output (shown with |...| delimiters)

Values are wrapped in | | so the exact output produced by CUBRID is visible
and verifiable. NUMERIC/DECIMAL is used instead of float to keep output exact.
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


def format_dates(cursor):
    cursor.execute(
        """
        SELECT
            TO_CHAR(DATE '2026-01-15', 'DD/MM/YYYY'),
            TO_CHAR(DATE '2026-01-15', 'MM-DD-YYYY'),
            TO_CHAR(DATETIME '2026-01-15 14:05:09', 'YYYY/MM/DD HH24:MI:SS')
        """
    )
    dmy, mdy, dt = cursor.fetchone()
    print("\nTO_CHAR date/datetime formatting (| | shows exact output):")
    print(f"  DD/MM/YYYY     |{dmy}|")
    print(f"  MM-DD-YYYY     |{mdy}|")
    print(f"  datetime       |{dt}|")



def parse_dates(cursor):
    cursor.execute(
        """
        SELECT
            TO_CHAR(TO_DATE('15-01-2026', 'DD-MM-YYYY'), 'YYYY/MM/DD'),
            TO_CHAR(TO_DATE('20260115', 'YYYYMMDD'), 'MM-DD-YYYY')
        """
    )
    a, b = cursor.fetchone()
    print("\nTO_DATE parsing (parse one layout, re-render in another):")
    print(f"  '15-01-2026' (DD-MM-YYYY) -> |{a}| (YYYY/MM/DD)")
    print(f"  '20260115'   (YYYYMMDD)  -> |{b}| (MM-DD-YYYY)")


def format_numbers(cursor):
    cursor.execute(
        """
        SELECT
            TO_CHAR(CAST(1234567.89 AS NUMERIC(12,2)), '9,999,999.99'),
            TO_CHAR(CAST(1234567.89 AS NUMERIC(12,2)), '999,999,999.99'),
            TO_CHAR(CAST(1234567.89 AS NUMERIC(12,2)), '099,999,999.99')
        """
    )
    grouped, padded, zero = cursor.fetchone()
    print("\nTO_CHAR numeric formatting (| | shows padding):")
    print(f"  grouped        |{grouped}|")
    print(f"  space-padded   |{padded}|")
    print(f"  zero-padded    |{zero}|")


if __name__ == "__main__":
    conn = get_connection()

    try:
        cursor = conn.cursor()
        format_dates(cursor)
        parse_dates(cursor)
        format_numbers(cursor)
        cursor.close()
    finally:
        conn.close()
