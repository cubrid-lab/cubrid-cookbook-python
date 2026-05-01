"""14_manual_cascade_delete.py — Application-managed cascade deletes.

Demonstrates:
- Tenant graph across accounts -> projects -> tasks -> comments
- Pre-delete impact preview counts
- Child-first transactional delete sequence
- Post-delete orphan verification
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
    cursor.execute("DROP TABLE IF EXISTS cookbook_comments")
    cursor.execute("DROP TABLE IF EXISTS cookbook_tasks")
    cursor.execute("DROP TABLE IF EXISTS cookbook_projects")
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")

    cursor.execute("""
        CREATE TABLE cookbook_accounts (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            name        VARCHAR(120) NOT NULL,
            is_active   INT NOT NULL DEFAULT 1,
            created_at  DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE cookbook_projects (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            account_id  INT NOT NULL,
            title       VARCHAR(160) NOT NULL,
            created_at  DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE cookbook_tasks (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            project_id  INT NOT NULL,
            title       VARCHAR(160) NOT NULL,
            is_done     INT NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE cookbook_comments (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            task_id    INT NOT NULL,
            body       VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL
        )
    """)
    conn.commit()
    cursor.close()
    print("✓ Created tenant graph tables")


def seed_account_graph(conn) -> int:
    cursor = conn.cursor()
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)

    cursor.execute(
        "INSERT INTO cookbook_accounts (name, is_active, created_at) VALUES (?, ?, ?)",
        ("Acme Tenant", 1, now),
    )
    account_id = cursor.lastrowid

    for p in range(1, 3):
        cursor.execute(
            """
            INSERT INTO cookbook_projects (account_id, title, created_at)
            VALUES (?, ?, ?)
            """,
            (account_id, f"Project-{p}", now),
        )
        project_id = cursor.lastrowid

        for t in range(1, 4):
            cursor.execute(
                """
                INSERT INTO cookbook_tasks (project_id, title, is_done, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, f"Task-{p}-{t}", 1 if t % 2 == 0 else 0, now),
            )
            task_id = cursor.lastrowid

            for c in range(1, 3):
                cursor.execute(
                    """
                    INSERT INTO cookbook_comments (task_id, body, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (task_id, f"Comment-{p}-{t}-{c}", now),
                )

    conn.commit()
    cursor.close()
    print(f"✓ Seeded account graph for account_id={account_id}")
    return account_id


def preview_delete(cursor, account_id: int) -> tuple[int, int, int, int]:
    cursor.execute("SELECT COUNT(*) FROM cookbook_accounts WHERE id = ?", (account_id,))
    accounts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_projects WHERE account_id = ?", (account_id,))
    projects = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_tasks t
        JOIN cookbook_projects p ON p.id = t.project_id
        WHERE p.account_id = ?
        """,
        (account_id,),
    )
    tasks = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_comments c
        JOIN cookbook_tasks t ON t.id = c.task_id
        JOIN cookbook_projects p ON p.id = t.project_id
        WHERE p.account_id = ?
        """,
        (account_id,),
    )
    comments = cursor.fetchone()[0]

    print("\n=== Delete Preview ===")
    print(f"  account_id={account_id}")
    print(f"  accounts: {accounts}")
    print(f"  projects: {projects}")
    print(f"  tasks:    {tasks}")
    print(f"  comments: {comments}")
    return accounts, projects, tasks, comments


def delete_account(cursor, account_id: int) -> tuple[int, int, int, int]:
    # CUBRID uses implicit transactions — no BEGIN WORK needed

    cursor.execute(
        """
        DELETE FROM cookbook_comments
        WHERE task_id IN (
            SELECT t.id
            FROM cookbook_tasks t
            JOIN cookbook_projects p ON p.id = t.project_id
            WHERE p.account_id = ?
        )
        """,
        (account_id,),
    )
    deleted_comments = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM cookbook_tasks
        WHERE project_id IN (
            SELECT id FROM cookbook_projects WHERE account_id = ?
        )
        """,
        (account_id,),
    )
    deleted_tasks = cursor.rowcount

    cursor.execute("DELETE FROM cookbook_projects WHERE account_id = ?", (account_id,))
    deleted_projects = cursor.rowcount

    cursor.execute("DELETE FROM cookbook_accounts WHERE id = ?", (account_id,))
    deleted_accounts = cursor.rowcount

    print("\n=== Delete Execution ===")
    print(f"  ✓ Deleted comments: {deleted_comments}")
    print(f"  ✓ Deleted tasks:    {deleted_tasks}")
    print(f"  ✓ Deleted projects: {deleted_projects}")
    print(f"  ✓ Deleted accounts: {deleted_accounts}")

    return deleted_comments, deleted_tasks, deleted_projects, deleted_accounts


def verify_cleanup(cursor, account_id: int) -> None:
    cursor.execute("SELECT COUNT(*) FROM cookbook_accounts WHERE id = ?", (account_id,))
    accounts_left = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cookbook_projects WHERE account_id = ?", (account_id,))
    projects_left = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_tasks t
        JOIN cookbook_projects p ON p.id = t.project_id
        WHERE p.account_id = ?
        """,
        (account_id,),
    )
    tasks_left = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_comments c
        JOIN cookbook_tasks t ON t.id = c.task_id
        JOIN cookbook_projects p ON p.id = t.project_id
        WHERE p.account_id = ?
        """,
        (account_id,),
    )
    comments_left = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_comments c
        LEFT JOIN cookbook_tasks t ON t.id = c.task_id
        WHERE t.id IS NULL
        """
    )
    orphan_comments = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM cookbook_tasks t
        LEFT JOIN cookbook_projects p ON p.id = t.project_id
        WHERE p.id IS NULL
        """
    )
    orphan_tasks = cursor.fetchone()[0]

    print("\n=== Post-Delete Verification ===")
    print(f"  account rows left: {accounts_left}")
    print(f"  project rows left: {projects_left}")
    print(f"  task rows left:    {tasks_left}")
    print(f"  comment rows left: {comments_left}")
    print(f"  orphan tasks:      {orphan_tasks}")
    print(f"  orphan comments:   {orphan_comments}")
    if accounts_left == 0 and projects_left == 0 and tasks_left == 0 and comments_left == 0:
        print("  ✓ Cascade cleanup verified")


def cleanup(conn) -> None:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS cookbook_comments")
    cursor.execute("DROP TABLE IF EXISTS cookbook_tasks")
    cursor.execute("DROP TABLE IF EXISTS cookbook_projects")
    cursor.execute("DROP TABLE IF EXISTS cookbook_accounts")
    conn.commit()
    cursor.close()
    print("\n✓ Cleaned up tenant graph tables")


if __name__ == "__main__":
    conn = get_connection()
    account_id = -1
    try:
        setup_schema(conn)
        account_id = seed_account_graph(conn)

        cursor = conn.cursor()
        preview_delete(cursor, account_id)
        delete_account(cursor, account_id)
        conn.commit()
        verify_cleanup(cursor, account_id)
        cursor.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        cleanup(conn)
        conn.close()
