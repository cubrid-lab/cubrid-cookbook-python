"""06_lob.py — Large Object (BLOB/CLOB) handling with pycubrid.

Demonstrates:
- Creating CLOB columns and inserting text data
- Creating BLOB columns and inserting binary data
- Reading LOB data back via the Lob handle
- Working with large text documents
"""

from __future__ import annotations

import pycubrid
from pycubrid.lob import Lob

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
    cursor.execute("DROP TABLE IF EXISTS cookbook_documents")
    cursor.execute("""
        CREATE TABLE cookbook_documents (
            id      INT AUTO_INCREMENT PRIMARY KEY,
            title   VARCHAR(200) NOT NULL,
            content CLOB
        )
    """)
    cursor.execute("DROP TABLE IF EXISTS cookbook_files")
    cursor.execute("""
        CREATE TABLE cookbook_files (
            id       INT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(200) NOT NULL,
            file_data BLOB
        )
    """)
    conn.commit()
    cursor.close()


def read_lob(conn: pycubrid.Connection, lob_dict: dict) -> bytes:
    """Read LOB content from a LOB result dictionary.

    When selecting LOB columns, pycubrid returns a dict with keys:
    lob_type, lob_length, file_locator, packed_lob_handle.
    Reconstruct a Lob object and read the data.
    """
    lob = Lob(conn, lob_dict["lob_type"], lob_dict["packed_lob_handle"])
    return lob.read(lob_dict["lob_length"])


def clob_example(conn: pycubrid.Connection) -> None:
    """Store and retrieve text data using CLOB."""
    print("=== CLOB (Character Large Object) ===")
    cursor = conn.cursor()

    # Insert text documents — strings can be inserted directly into CLOB columns
    documents = [
        (
            "README",
            "# CUBRID Cookbook\n\nA collection of examples for CUBRID database.",
        ),
        ("License", "Apache License 2.0\n\nCopyright 2026 cubrid-labs"),
        (
            "Long Text",
            "Lorem ipsum dolor sit amet. " * 100,  # ~3KB of text
        ),
    ]

    for title, content in documents:
        cursor.execute(
            "INSERT INTO cookbook_documents (title, content) VALUES (?, ?)",
            (title, content),
        )
    conn.commit()
    print(f"  ✓ Inserted {len(documents)} documents with CLOB data")

    # Read back — CLOB columns return a dict with LOB metadata
    cursor.execute("SELECT title, content FROM cookbook_documents ORDER BY id")
    for row in cursor.fetchall():
        title = row[0]
        clob_dict = row[1]
        if clob_dict and isinstance(clob_dict, dict):
            text = read_lob(conn, clob_dict).decode("utf-8")
        else:
            text = ""
        preview = text[:60] + "..." if len(text) > 60 else text
        print(f"  {title:15s} ({len(text):,d} chars): {preview}")

    cursor.close()


def blob_example(conn: pycubrid.Connection) -> None:
    """Store and retrieve binary data using BLOB."""
    print("\n=== BLOB (Binary Large Object) ===")
    cursor = conn.cursor()

    # Create some binary data — bytes can be inserted directly into BLOB columns
    files = [
        ("icon.bin", bytes(range(256))),  # 256 bytes
        ("sample.bin", b"\x00\x01\x02" * 1000),  # 3KB
        ("empty.bin", b""),  # Empty BLOB
    ]

    for filename, file_data in files:
        if file_data:
            cursor.execute(
                "INSERT INTO cookbook_files (filename, file_data) VALUES (?, ?)",
                (filename, file_data),
            )
        else:
            cursor.execute(
                "INSERT INTO cookbook_files (filename, file_data) VALUES (?, NULL)",
                (filename,),
            )
    conn.commit()
    print(f"  ✓ Inserted {len(files)} files with BLOB data")

    # Read back — BLOB columns return a dict with LOB metadata
    cursor.execute("SELECT filename, file_data FROM cookbook_files ORDER BY id")
    for row in cursor.fetchall():
        filename = row[0]
        blob_dict = row[1]
        if blob_dict is not None and isinstance(blob_dict, dict):
            data = read_lob(conn, blob_dict)
            print(f"  {filename:15s} ({len(data):,d} bytes)")
        else:
            print(f"  {filename:15s} (NULL)")

    cursor.close()


def cleanup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_documents")
    cursor.execute("DROP TABLE IF EXISTS cookbook_files")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup(conn)
        clob_example(conn)
        blob_example(conn)
    finally:
        cleanup(conn)
        conn.close()
