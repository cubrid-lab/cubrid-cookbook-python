"""04_transaction.py — Transaction patterns: Java JDBC → Python pycubrid.

Migration from Java try/catch/finally transaction management to Python patterns.

Java JDBC transaction pattern (what you're replacing):
──────────────────────────────────────────────────────
    Connection conn = null;
    try {
        conn = DriverManager.getConnection(url, "dba", "");
        conn.setAutoCommit(false);

        PreparedStatement ps = conn.prepareStatement("UPDATE ...");
        ps.executeUpdate();

        conn.commit();
    } catch (SQLException e) {
        if (conn != null) conn.rollback();
        throw e;
    } finally {
        if (conn != null) conn.close();
    }

Python pycubrid (what you'll write):
─────────────────────────────────────
    conn = pycubrid.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE ...")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

Same pattern, less ceremony. Python's auto-commit OFF default matches
the explicit conn.setAutoCommit(false) you'd write in Java.
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


def setup(conn: Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")
    cursor.execute("""
        CREATE TABLE cookbook_accounts (
            id      INT AUTO_INCREMENT PRIMARY KEY,
            owner   VARCHAR(100) NOT NULL,
            balance DOUBLE DEFAULT 0.0
        )
    """)
    cursor.execute("INSERT INTO cookbook_accounts (owner, balance) VALUES ('Alice', 1000.0)")
    cursor.execute("INSERT INTO cookbook_accounts (owner, balance) VALUES ('Bob', 500.0)")
    cursor.execute("INSERT INTO cookbook_accounts (owner, balance) VALUES ('Charlie', 750.0)")
    conn.commit()
    cursor.close()
    print("Setup: 3 accounts created")


def show_balances(conn: Connection, label: str = "") -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT owner, balance FROM cookbook_accounts ORDER BY id")
    rows = cursor.fetchall()
    tag = f" [{label}]" if label else ""
    print(f"  Balances{tag}: {', '.join(f'{r[0]}=${r[1]:.2f}' for r in rows)}")
    cursor.close()


def commit_and_rollback(conn: Connection) -> None:
    """Basic commit and rollback.

    Java equivalent:
        conn.setAutoCommit(false);
        try {
            // ... execute statements ...
            conn.commit();
        } catch (SQLException e) {
            conn.rollback();
        }

    Key difference: Python auto-commit is already OFF by default.
    """
    print("\n=== Commit ===")
    show_balances(conn, "before")

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance - ? WHERE owner = ?",
        (200.0, "Alice"),
    )
    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?",
        (200.0, "Bob"),
    )
    conn.commit()
    print("  Transferred $200 Alice -> Bob")
    show_balances(conn, "after commit")
    cursor.close()

    print("\n=== Rollback ===")
    cursor = conn.cursor()
    cursor.execute("UPDATE cookbook_accounts SET balance = 0 WHERE owner = 'Alice'")
    print("  Set Alice=0 (not committed)")
    conn.rollback()
    print("  Rolled back")
    show_balances(conn, "after rollback")
    cursor.close()


def safe_transfer(conn: Connection, sender: str, receiver: str, amount: float) -> bool:
    """Transfer with proper error handling.

    Java equivalent (try/catch/finally):
        Connection conn = null;
        try {
            conn = ds.getConnection();
            conn.setAutoCommit(false);

            PreparedStatement debit = conn.prepareStatement(
                "UPDATE cookbook_accounts SET balance = balance - ? WHERE owner = ? AND balance >= ?"
            );
            debit.setDouble(1, amount);
            debit.setString(2, sender);
            debit.setDouble(3, amount);
            int affected = debit.executeUpdate();

            if (affected == 0) {
                conn.rollback();
                return false;
            }

            PreparedStatement credit = conn.prepareStatement(
                "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?"
            );
            credit.setDouble(1, amount);
            credit.setString(2, receiver);
            credit.executeUpdate();

            conn.commit();
            return true;
        } catch (SQLException e) {
            if (conn != null) conn.rollback();
            throw e;
        } finally {
            if (conn != null) conn.close();
        }

    Python — same logic, 60% less code:
    """
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE cookbook_accounts SET balance = balance - ? WHERE owner = ? AND balance >= ?",
            (amount, sender, amount),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return False

        cursor.execute(
            "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?",
            (amount, receiver),
        )
        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()


def savepoint_pattern(conn: Connection) -> None:
    """Savepoints — partial rollback within a transaction.

    Java:
        conn.setAutoCommit(false);
        Statement stmt = conn.createStatement();

        stmt.executeUpdate("UPDATE ...");
        Savepoint sp = conn.setSavepoint("after_step1");

        stmt.executeUpdate("UPDATE ...");  // risky operation
        conn.rollback(sp);  // undo only step 2

        conn.commit();  // step 1 is preserved

    Python — SQL-level savepoints (CUBRID supports them):
    """
    print("\n=== Savepoints ===")
    show_balances(conn, "before")

    cursor = conn.cursor()

    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?",
        (100.0, "Alice"),
    )
    print("  Step 1: Alice +$100")

    cursor.execute("SAVEPOINT after_alice_bonus")

    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?",
        (999.0, "Bob"),
    )
    print("  Step 2: Bob +$999 (will undo)")

    cursor.execute("ROLLBACK TO SAVEPOINT after_alice_bonus")
    print("  Rolled back to savepoint (Bob's $999 undone)")

    conn.commit()
    show_balances(conn, "after savepoint commit")
    cursor.close()


def autocommit_pattern() -> None:
    """Auto-commit mode comparison.

    Java:
        conn.setAutoCommit(true);   // Default in JDBC
        stmt.executeUpdate("UPDATE ...");  // Committed immediately

    Python:
        conn.autocommit = True      // Must opt-in (default is OFF)
        cursor.execute("UPDATE ...")  // Committed immediately

    WARNING: Java defaults to auto-commit ON, Python defaults to OFF.
    This is the #1 source of migration bugs. Be explicit.
    """
    print("\n=== Auto-commit Mode ===")

    conn = get_connection()
    print(f"  Default autocommit: {conn.autocommit}")

    conn.autocommit = True

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance + ? WHERE owner = ?",
        (1.0, "Charlie"),
    )
    print("  Charlie +$1 (auto-committed, no explicit commit needed)")

    show_balances(conn, "autocommit")

    conn.autocommit = False
    cursor.close()
    conn.close()


def cleanup(conn: Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")
    conn.commit()
    cursor.close()
    print("\nCleaned up")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup(conn)
        commit_and_rollback(conn)

        print("\n=== Safe Transfer ===")
        show_balances(conn, "before transfers")
        ok = safe_transfer(conn, "Alice", "Charlie", 100.0)
        print(f"  Transfer Alice->Charlie $100: {'success' if ok else 'failed'}")
        ok = safe_transfer(conn, "Bob", "Alice", 9999.0)
        print(f"  Transfer Bob->Alice $9999: {'success' if ok else 'failed (insufficient)'}")
        show_balances(conn, "after transfers")

        savepoint_pattern(conn)
        autocommit_pattern()
    finally:
        cleanup(conn)
        conn.close()
