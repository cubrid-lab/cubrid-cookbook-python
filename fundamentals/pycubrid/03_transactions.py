"""03_transactions.py — Transaction management with pycubrid.

Demonstrates:
- Manual commit/rollback
- Autocommit mode
- Savepoints (SAVEPOINT, ROLLBACK TO SAVEPOINT)
- Transaction isolation
"""

from __future__ import annotations

import pycubrid

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
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")
    cursor.execute("""
        CREATE TABLE cookbook_accounts (
            id      INT AUTO_INCREMENT PRIMARY KEY,
            name    VARCHAR(100) NOT NULL,
            balance DOUBLE DEFAULT 0.0
        )
    """)
    cursor.execute("INSERT INTO cookbook_accounts (name, balance) VALUES ('Alice', 1000.0)")
    cursor.execute("INSERT INTO cookbook_accounts (name, balance) VALUES ('Bob', 500.0)")
    conn.commit()
    cursor.close()


def show_balances(conn: pycubrid.Connection, label: str = "") -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT name, balance FROM cookbook_accounts ORDER BY id")
    rows = cursor.fetchall()
    tag = f" ({label})" if label else ""
    print(f"  Balances{tag}: {', '.join(f'{r[0]}=${r[1]:.2f}' for r in rows)}")
    cursor.close()


def commit_example(conn: pycubrid.Connection) -> None:
    """Transfer money with explicit commit."""
    print("\n=== Commit Example ===")
    show_balances(conn, "before")

    cursor = conn.cursor()
    amount = 200.0

    # Debit Alice
    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance - ? WHERE name = ?",
        (amount, "Alice"),
    )
    # Credit Bob
    cursor.execute(
        "UPDATE cookbook_accounts SET balance = balance + ? WHERE name = ?",
        (amount, "Bob"),
    )

    # Both changes are visible within this transaction
    conn.commit()
    print(f"  ✓ Transferred ${amount:.2f} from Alice to Bob")

    show_balances(conn, "after commit")
    cursor.close()


def rollback_example(conn: pycubrid.Connection) -> None:
    """Demonstrate rollback — changes are discarded."""
    print("\n=== Rollback Example ===")
    show_balances(conn, "before")

    cursor = conn.cursor()

    # Make a bad update
    cursor.execute("UPDATE cookbook_accounts SET balance = 0 WHERE name = 'Alice'")
    print("  Made Alice's balance = 0 (not committed)")

    # Oops — rollback!
    conn.rollback()
    print("  ✓ Rolled back — Alice's balance restored")

    show_balances(conn, "after rollback")
    cursor.close()


def autocommit_example() -> None:
    """Autocommit mode — each statement commits immediately."""
    print("\n=== Autocommit Example ===")
    conn = get_connection()
    conn.autocommit = True

    cursor = conn.cursor()
    cursor.execute("UPDATE cookbook_accounts SET balance = balance + 50 WHERE name = 'Alice'")
    print("  ✓ Updated Alice +$50 (auto-committed immediately)")

    # No need to call conn.commit()
    show_balances(conn, "autocommit")

    conn.autocommit = False  # Back to manual mode
    cursor.close()
    conn.close()


def savepoint_example(conn: pycubrid.Connection) -> None:
    """Savepoints — partial rollback within a transaction."""
    print("\n=== Savepoint Example ===")
    show_balances(conn, "before")

    cursor = conn.cursor()

    # Step 1: Give Alice a bonus
    cursor.execute("UPDATE cookbook_accounts SET balance = balance + 100 WHERE name = 'Alice'")
    print("  Step 1: Alice +$100")

    # Create savepoint after step 1
    cursor.execute("SAVEPOINT after_alice_bonus")
    print("  ✓ Created SAVEPOINT 'after_alice_bonus'")

    # Step 2: Give Bob a bonus (we'll undo this)
    cursor.execute("UPDATE cookbook_accounts SET balance = balance + 999 WHERE name = 'Bob'")
    print("  Step 2: Bob +$999 (will be rolled back)")

    # Rollback to savepoint — undoes step 2 but keeps step 1
    cursor.execute("ROLLBACK TO SAVEPOINT after_alice_bonus")
    print("  ✓ Rolled back to savepoint — Bob's $999 undone, Alice's $100 kept")

    conn.commit()
    show_balances(conn, "after savepoint rollback + commit")
    cursor.close()


def cleanup(conn: pycubrid.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    conn = get_connection()

    try:
        setup(conn)
        commit_example(conn)
        rollback_example(conn)
        autocommit_example()
        savepoint_example(conn)
    finally:
        cleanup(conn)
        conn.close()
