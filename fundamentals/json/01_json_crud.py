"""01_json_crud.py - Native JSON column CRUD with CUBRID 10.2+ and pycubrid.

Demonstrates:
- CREATE TABLE with a JSON column
- INSERT JSON documents via parameterized queries
- Query JSON with JSON_EXTRACT and JSON_UNQUOTE (CUBRID quirk)
- Update and delete rows based on JSON path predicates
- Aggregate JSON array elements with JSON_LENGTH

CUBRID's JSON support (since 10.2) stores JSON as text and provides
JSON_EXTRACT / JSON_INSERT / JSON_REPLACE / JSON_REMOVE path functions.
The most important gotcha: JSON_EXTRACT returns a JSON-typed value, so
strings come back DOUBLE-QUOTED. Use JSON_UNQUOTE(JSON_EXTRACT(...)) to
strip the outer quotes when you want the raw scalar value.

Run:
    python 01_json_crud.py
"""

from __future__ import annotations

import json
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


def get_connection() -> Any:
    return pycubrid.connect(**DB_CONFIG)


def setup_schema(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_user_prefs")
    cur.execute(
        """
        CREATE TABLE cookbook_user_prefs (
            user_id      INT PRIMARY KEY,
            email        VARCHAR(200) NOT NULL,
            preferences  JSON NOT NULL,
            created_at   DATETIME NOT NULL DEFAULT SYS_DATETIME
        )
        """
    )
    conn.commit()
    cur.close()
    print("[setup] Created cookbook_user_prefs with JSON column")


def cleanup(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS cookbook_user_prefs")
    conn.commit()
    cur.close()


def main() -> None:
    print("=== JSON Type CRUD Demo (CUBRID 10.2+) ===")
    print()

    conn = get_connection()
    try:
        setup_schema(conn)
        cur = conn.cursor()

        # ------------------------------------------------------------------
        # INSERT: pass JSON as a string parameter. pycubrid binds it as a
        # literal string; CUBRID validates and stores it as JSON.
        # ------------------------------------------------------------------
        docs = [
            (
                1,
                "alice@example.com",
                json.dumps({"theme": "dark", "newsletter": True, "tags": ["python", "cubrid"]}),
            ),
            (
                2,
                "bob@example.com",
                json.dumps({"theme": "light", "newsletter": False, "tags": ["java"]}),
            ),
            (
                3,
                "carol@example.com",
                json.dumps({"theme": "dark", "newsletter": True, "tags": ["python", "rust", "go"]}),
            ),
        ]
        cur.executemany(
            "INSERT INTO cookbook_user_prefs (user_id, email, preferences) VALUES (?, ?, ?)",
            docs,
        )
        conn.commit()
        print(f"[1] Inserted {len(docs)} JSON documents")

        # ------------------------------------------------------------------
        # SELECT raw JSON: read back the whole preferences column.
        # ------------------------------------------------------------------
        cur.execute("SELECT user_id, email, preferences FROM cookbook_user_prefs ORDER BY user_id")
        print()
        print("[2] All rows (raw JSON):")
        for row in cur.fetchall():
            print(f"    user_id={row[0]}  email={row[1]}")
            print(f"    preferences={row[2]}")

        # ------------------------------------------------------------------
        # GOTCHA: JSON_EXTRACT returns strings DOUBLE-QUOTED.
        #
        # Path syntax: $.key  (dot notation, SQL/JSON path standard)
        # ------------------------------------------------------------------
        print()
        print("[3] JSON_EXTRACT('$.theme') — RAW (note the double quotes):")
        cur.execute(
            "SELECT user_id, JSON_EXTRACT(preferences, '$.theme') AS theme_raw "
            "FROM cookbook_user_prefs ORDER BY user_id"
        )
        for row in cur.fetchall():
            print(f"    user_id={row[0]}  theme_raw={row[1]!r}")

        # ------------------------------------------------------------------
        # FIX: wrap with JSON_UNQUOTE to strip the outer JSON quotes.
        # ------------------------------------------------------------------
        print()
        print("[4] JSON_UNQUOTE(JSON_EXTRACT(...)) — clean scalar value:")
        cur.execute(
            "SELECT user_id, JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.theme')) AS theme "
            "FROM cookbook_user_prefs ORDER BY user_id"
        )
        for row in cur.fetchall():
            print(f"    user_id={row[0]}  theme={row[1]!r}")

        # ------------------------------------------------------------------
        # FILTER: WHERE clause on JSON path.
        # ------------------------------------------------------------------
        print()
        print("[5] Users with theme='dark':")
        cur.execute(
            "SELECT user_id, email "
            "FROM cookbook_user_prefs "
            "WHERE JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.theme')) = 'dark' "
            "ORDER BY user_id"
        )
        for row in cur.fetchall():
            print(f"    user_id={row[0]}  email={row[1]}")

        # ------------------------------------------------------------------
        # ARRAY: JSON_LENGTH on a JSON array inside the document.
        # ------------------------------------------------------------------
        print()
        print("[6] Tag count per user (JSON_LENGTH on '$.tags'):")
        cur.execute(
            "SELECT user_id, JSON_LENGTH(JSON_EXTRACT(preferences, '$.tags')) AS tag_count "
            "FROM cookbook_user_prefs ORDER BY user_id"
        )
        for row in cur.fetchall():
            print(f"    user_id={row[0]}  tag_count={row[1]}")

        # ------------------------------------------------------------------
        # UPDATE: modify a JSON path in place with JSON_REPLACE.
        # ------------------------------------------------------------------
        print()
        cur.execute(
            "UPDATE cookbook_user_prefs "
            "SET preferences = JSON_REPLACE(preferences, '$.theme', '\"light\"') "
            "WHERE user_id = ?",
            (1,),
        )
        conn.commit()
        cur.execute(
            "SELECT JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.theme')) "
            "FROM cookbook_user_prefs WHERE user_id = ?",
            (1,),
        )
        row = cur.fetchone()
        print(f"[7] After UPDATE: user_id=1 theme is now {row[0]!r}")

        # ------------------------------------------------------------------
        # DELETE: remove rows based on JSON predicate.
        # ------------------------------------------------------------------
        cur.execute(
            "DELETE FROM cookbook_user_prefs "
            "WHERE JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.newsletter')) = 'false'"
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM cookbook_user_prefs")
        remaining = cur.fetchone()[0]
        print(f"[8] After DELETE (newsletter=false): {remaining} rows remain")

        cur.close()
    finally:
        try:
            cleanup(conn)
        finally:
            conn.close()

    print()
    print("--- JSON function cheat sheet ---")
    print("  JSON_EXTRACT(doc, '$.path')            raw value (JSON-typed)")
    print("  JSON_UNQUOTE(JSON_EXTRACT(doc, '$.x')) scalar value (no quotes)")
    print("  JSON_LENGTH(doc_or_array)              element count")
    print("  JSON_REPLACE(doc, '$.k', new_value)    update existing key")
    print("  JSON_INSERT(doc, '$.k', value)         add key if absent")
    print("  JSON_REMOVE(doc, '$.k')                delete key")
    print()
    print("Path syntax:  $.key        object key")
    print("              $.key[0]     array index")
    print("              $.key.sub    nested key")


if __name__ == "__main__":
    try:
        main()
    except DatabaseError as exc:
        print(f"Database error: {exc}")
        raise SystemExit(1) from exc
