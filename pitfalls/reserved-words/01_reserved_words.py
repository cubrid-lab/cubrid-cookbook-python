"""01_reserved_words.py - Live check of the reserved-word advice in pitfalls/README.md.

Demonstrates:
- Unquoted reserved words (``key``, ``value``) are rejected as column names
- Renaming only ``value`` is NOT enough: ``key`` is reserved too
- The corrected DDL (``setting_key``, ``val``) works
- Reserved words work as identifiers when quoted with double quotes, square
  brackets or backticks
- ``name`` is not a reserved word and needs no renaming or quoting

The reserved-word list is the official one for the supported server versions,
for example https://www.cubrid.org/manual/en/11.2/sql/keyword.html and
https://www.cubrid.org/manual/en/11.4/sql/keyword.html .

Run:
    python 01_reserved_words.py
"""

from __future__ import annotations

from typing import Any

import pycubrid  # type: ignore[import-not-found]
from pycubrid import DatabaseError  # type: ignore[import-not-found]

DB_CONFIG: dict[str, Any] = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}

TABLE = "cookbook_settings"

# (label, column definitions) pairs, in the order pitfalls/README.md shows them.
CASES: list[tuple[str, str]] = [
    ("anti-pattern: key, value", "key VARCHAR(50), value VARCHAR(255)"),
    ("value renamed only: key, val", "key VARCHAR(50), val VARCHAR(255)"),
    ("corrected: setting_key, val", "setting_key VARCHAR(50), val VARCHAR(255)"),
    ('double quotes: "key", "value"', '"key" VARCHAR(50), "value" VARCHAR(255)'),
    ("square brackets: [key], [value]", "[key] VARCHAR(50), [value] VARCHAR(255)"),
    ("backticks: `key`, `value`", "`key` VARCHAR(50), `value` VARCHAR(255)"),
    ("not reserved: name", "name VARCHAR(50), val VARCHAR(255)"),
]


def try_create(cur: Any, columns: str) -> str:
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    try:
        cur.execute(f"CREATE TABLE {TABLE} ({columns})")
    except DatabaseError as exc:
        # Print only the exception class: the server's message text is not
        # stable across CUBRID versions.
        return f"rejected ({type(exc).__name__})"
    return "created"


def main() -> None:
    print("=== CUBRID reserved words as column names ===")
    print()
    conn = pycubrid.connect(**DB_CONFIG)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        for label, columns in CASES:
            print(f"  {label:34s} -> {try_create(cur, columns)}")

        # Round-trip data through the corrected DDL.
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(f"CREATE TABLE {TABLE} (setting_key VARCHAR(50), val VARCHAR(255))")
        cur.execute(f"INSERT INTO {TABLE} (setting_key, val) VALUES (?, ?)", ("theme", "dark"))
        cur.execute(f"SELECT setting_key, val FROM {TABLE}")
        print()
        print(f"  corrected DDL round-trip: {cur.fetchall()}")

        # Round-trip data through quoted reserved words; every statement quotes them.
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(f'CREATE TABLE {TABLE} ("key" VARCHAR(50), "value" VARCHAR(255))')
        cur.execute(f'INSERT INTO {TABLE} ("key", "value") VALUES (?, ?)', ("theme", "dark"))
        cur.execute(f'SELECT "key", "value" FROM {TABLE}')
        print(f"  quoted DDL round-trip:    {cur.fetchall()}")

        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
