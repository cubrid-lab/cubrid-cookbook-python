"""02_crud_dbapi.py — CRUD with raw DB-API: Java JDBC → Python pycubrid.

Side-by-side migration from Java JDBC PreparedStatement to Python DB-API.
Each function shows the Java equivalent in its docstring.

Java JDBC pattern (what you're replacing):
──────────────────────────────────────────
    PreparedStatement ps = conn.prepareStatement(
        "INSERT INTO cookbook_items (val, cnt) VALUES (?, ?)"
    );
    ps.setString(1, "widget");
    ps.setInt(2, 10);
    ps.executeUpdate();
    conn.commit();
    ps.close();

Python pycubrid (what you'll write):
─────────────────────────────────────
    cursor.execute(
        "INSERT INTO cookbook_items (val, cnt) VALUES (?, ?)",
        ("widget", 10),
    )
    conn.commit()

Same parameter marker (?), same SQL, 60% less boilerplate.
"""

from __future__ import annotations

import pycubrid
from pycubrid.connection import Connection

DB_CONFIG = {
    "host": "localhost",
    "port": 33000,
    "database": "testdb",
    "user": "dba",
    "password": "",
}


def get_connection() -> Connection:
    return pycubrid.connect(**DB_CONFIG)


def setup_table(conn: Connection) -> None:
    """CREATE TABLE — identical SQL in both languages.

    Java:
        stmt.executeUpdate("CREATE TABLE cookbook_items (...)");
        conn.commit();
    """
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_items")
    cursor.execute("""
        CREATE TABLE cookbook_items (
            id   INT AUTO_INCREMENT PRIMARY KEY,
            val  VARCHAR(200) NOT NULL,
            cnt  INT DEFAULT 0,
            price DOUBLE DEFAULT 0.0
        )
    """)
    conn.commit()
    cursor.close()
    print("Created table 'cookbook_items'")


def insert_single(conn: Connection) -> None:
    """INSERT one row with parameters.

    Java (PreparedStatement):
        PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO cookbook_items (val, cnt, price) VALUES (?, ?, ?)"
        );
        ps.setString(1, "Widget A");
        ps.setInt(2, 10);
        ps.setDouble(3, 29.99);
        ps.executeUpdate();
        conn.commit();
        ps.close();

    Python — parameter tuple replaces setString/setInt/setDouble:
    """
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cookbook_items (val, cnt, price) VALUES (?, ?, ?)",
        ("Widget A", 10, 29.99),
    )
    conn.commit()
    cursor.close()
    print("Inserted 1 row")


def insert_multiple(conn: Connection) -> None:
    """INSERT multiple rows.

    Java:
        for (Object[] row : data) {
            ps.setString(1, (String) row[0]);
            ps.setInt(2, (Integer) row[1]);
            ps.setDouble(3, (Double) row[2]);
            ps.executeUpdate();
        }
        conn.commit();

    Python — executemany replaces the loop entirely:
    """
    items = [
        ("Widget B", 5, 19.99),
        ("Gadget C", 20, 49.99),
        ("Part D", 100, 2.50),
        ("Tool E", 8, 34.99),
    ]
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO cookbook_items (val, cnt, price) VALUES (?, ?, ?)",
        items,
    )
    conn.commit()
    cursor.close()
    print(f"Inserted {len(items)} rows")


def select_all(conn: Connection) -> list[tuple]:
    """SELECT all rows.

    Java (ResultSet iteration):
        ResultSet rs = stmt.executeQuery("SELECT id, val, cnt, price FROM ...");
        while (rs.next()) {
            int id = rs.getInt("id");
            String val = rs.getString("val");
            int cnt = rs.getInt("cnt");
            double price = rs.getDouble("price");
        }
        rs.close();

    Python — fetchall() returns a list of tuples, no getInt/getString:
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, val, cnt, price FROM cookbook_items ORDER BY id")
    rows = cursor.fetchall()

    print(f"\nAll items ({len(rows)} rows):")
    print(f"  {'ID':>3s}  {'Value':12s}  {'Count':>5s}  {'Price':>8s}")
    for row in rows:
        print(f"  {row[0]:3d}  {row[1]:12s}  {row[2]:5d}  ${row[3]:7.2f}")

    cursor.close()
    return rows


def select_filtered(conn: Connection) -> None:
    """SELECT with WHERE and parameters.

    Java:
        PreparedStatement ps = conn.prepareStatement(
            "SELECT val, price FROM cookbook_items WHERE price > ? ORDER BY price DESC"
        );
        ps.setDouble(1, 20.0);
        ResultSet rs = ps.executeQuery();
        while (rs.next()) { ... }

    Python — same ? marker, parameters as tuple:
    """
    cursor = conn.cursor()

    cursor.execute(
        "SELECT val, price FROM cookbook_items WHERE price > ? ORDER BY price DESC",
        (20.0,),
    )
    rows = cursor.fetchall()

    print(f"\nItems over $20 ({len(rows)} rows):")
    for row in rows:
        print(f"  {row[0]:12s}  ${row[1]:.2f}")

    cursor.close()


def select_fetchone(conn: Connection) -> None:
    """Fetch one row at a time (replaces rs.next() pattern).

    Java:
        rs.next();  // moves cursor forward, returns boolean
        String val = rs.getString("val");

    Python — fetchone() returns tuple or None:
    """
    cursor = conn.cursor()
    cursor.execute("SELECT val, cnt FROM cookbook_items ORDER BY id")

    first = cursor.fetchone()
    print(f"\nFirst item: {first[0]} (count={first[1]})")

    second = cursor.fetchone()
    print(f"Second item: {second[0]} (count={second[1]})")

    cursor.close()


def update_rows(conn: Connection) -> None:
    """UPDATE rows.

    Java:
        PreparedStatement ps = conn.prepareStatement(
            "UPDATE cookbook_items SET price = ? WHERE val = ?"
        );
        ps.setDouble(1, 24.99);
        ps.setString(2, "Widget A");
        int affected = ps.executeUpdate();
        conn.commit();

    Python — cursor.rowcount replaces executeUpdate return value:
    """
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE cookbook_items SET price = ? WHERE val = ?",
        (24.99, "Widget A"),
    )
    print(f"\nUpdated Widget A price (rows affected: {cursor.rowcount})")

    cursor.execute(
        "UPDATE cookbook_items SET cnt = cnt + ? WHERE price < ?",
        (10, 10.0),
    )
    print(f"Restocked cheap items (rows affected: {cursor.rowcount})")

    conn.commit()
    cursor.close()


def delete_rows(conn: Connection) -> None:
    """DELETE rows.

    Java:
        PreparedStatement ps = conn.prepareStatement(
            "DELETE FROM cookbook_items WHERE val = ?"
        );
        ps.setString(1, "Tool E");
        int affected = ps.executeUpdate();
        conn.commit();
    """
    cursor = conn.cursor()

    cursor.execute("DELETE FROM cookbook_items WHERE val = ?", ("Tool E",))
    print(f"\nDeleted Tool E (rows affected: {cursor.rowcount})")

    conn.commit()
    cursor.close()


def handle_nulls(conn: Connection) -> None:
    """NULL handling — much simpler in Python.

    Java (the wasNull pattern):
        int cnt = rs.getInt("cnt");
        if (rs.wasNull()) {
            // cnt is actually null, not 0
        }

    Python — NULL becomes None, no wasNull() needed:
    """
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cookbook_items (val, cnt, price) VALUES (?, NULL, NULL)",
        ("NullTest",),
    )
    conn.commit()

    cursor.execute(
        "SELECT val, cnt, price FROM cookbook_items WHERE val = ?",
        ("NullTest",),
    )
    row = cursor.fetchone()
    print(f"\nNull handling: val={row[0]!r}, cnt={row[1]!r}, price={row[2]!r}")

    cursor.close()


def cleanup(conn: Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_items")
    conn.commit()
    cursor.close()
    print("\nCleaned up table 'cookbook_items'")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup_table(conn)
        insert_single(conn)
        insert_multiple(conn)
        select_all(conn)
        select_filtered(conn)
        select_fetchone(conn)
        update_rows(conn)
        select_all(conn)
        delete_rows(conn)
        select_all(conn)
        handle_nulls(conn)
    finally:
        cleanup(conn)
        conn.close()
