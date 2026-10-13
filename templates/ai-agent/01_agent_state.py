"""Agent state management — store sessions, messages, and tool calls.

CUBRID acts as the persistent state store for an AI agent:
- `cookbook_agent_sessions`: one row per conversation thread
- `cookbook_agent_messages`: individual turns (user / assistant / tool)
- `cookbook_agent_tool_calls`: structured records of every tool invocation

Demonstrates JSON columns for LLM I/O, SET for tagging,
and AUTO_INCREMENT for ordering.
"""

from __future__ import annotations

from contextlib import closing

import json
import os

import pycubrid

# Same CUBRID_* env vars as 02_mcp_toolchain.py, so a single live test
# instance (or a local dev CUBRID) configures every recipe in this folder.
DB_CONFIG = {
    "host": os.environ.get("CUBRID_HOST", "localhost"),
    "port": int(os.environ.get("CUBRID_PORT", "33000")),
    "user": os.environ.get("CUBRID_USER", "dba"),
    "password": os.environ.get("CUBRID_PASSWORD", ""),
    "database": os.environ.get("CUBRID_DATABASE", "testdb"),
}

# Recipe-owned session key: a rerun deletes only this session, never a
# reader's own sessions such as "demo-001".
DEMO_SESSION_KEY = "cookbook-agent-state-demo"

# ----------------------------------------------------------------
# Schema setup
# ----------------------------------------------------------------

DDL = [
    """
    CREATE TABLE IF NOT EXISTS cookbook_agent_sessions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_key VARCHAR(64) NOT NULL UNIQUE,
        agent_name VARCHAR(100) NOT NULL,
        status VARCHAR(20) DEFAULT 'active',
        tags SET(VARCHAR(50)),
        created_at DATETIME DEFAULT SYS_DATETIME,
        updated_at DATETIME DEFAULT SYS_DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cookbook_agent_messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        message_role VARCHAR(20) NOT NULL,
        content STRING,
        metadata JSON,
        created_at DATETIME DEFAULT SYS_DATETIME,
        FOREIGN KEY (session_id) REFERENCES cookbook_agent_sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cookbook_agent_tool_calls (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        tool_name VARCHAR(100) NOT NULL,
        arguments JSON,
        result JSON,
        status VARCHAR(20) DEFAULT 'pending',
        duration_ms INT,
        created_at DATETIME DEFAULT SYS_DATETIME,
        FOREIGN KEY (session_id) REFERENCES cookbook_agent_sessions(id)
    )
    """,
]


def setup_schema(conn: pycubrid.connection.Connection) -> None:
    cur = conn.cursor()
    for ddl in DDL:
        cur.execute(ddl)
    conn.commit()
    cur.close()


def delete_session(conn: pycubrid.connection.Connection, session_key: str) -> None:
    """Remove a session by key, with its messages and tool calls (children first).

    The demos use fixed keys; deleting the previous run's session first lets
    each recipe run again on the same database.
    """
    session_ids = "SELECT id FROM cookbook_agent_sessions WHERE session_key = ?"
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cookbook_agent_tool_calls WHERE session_id IN (" + session_ids + ")",
        [session_key],
    )
    cur.execute(
        "DELETE FROM cookbook_agent_messages WHERE session_id IN (" + session_ids + ")",
        [session_key],
    )
    cur.execute("DELETE FROM cookbook_agent_sessions WHERE session_key = ?", [session_key])
    conn.commit()
    cur.close()


def create_session(
    conn: pycubrid.connection.Connection,
    session_key: str,
    agent_name: str = "data-assistant",
    tags: list[str] | None = None,
) -> int:
    """Create a new agent session and return its ID."""
    cur = conn.cursor()
    tag_values = tags or []
    tag_set = "{" + ", ".join("?" for _ in tag_values) + "}"
    cur.execute(
        "INSERT INTO cookbook_agent_sessions (session_key, agent_name, tags) VALUES (?, ?, "
        + tag_set
        + ")",
        [session_key, agent_name, *tag_values],
    )
    session_id = cur.lastrowid
    if session_id is None:
        cur.close()
        conn.rollback()
        raise RuntimeError("Session INSERT did not return an auto-increment ID")
    conn.commit()
    cur.close()
    return session_id


def add_message(
    conn: pycubrid.connection.Connection,
    session_id: int,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> int:
    """Record one conversation turn."""
    cur = conn.cursor()
    meta_json = json.dumps(metadata) if metadata else None
    cur.execute(
        "INSERT INTO cookbook_agent_messages (session_id, message_role, content, metadata) VALUES (?, ?, ?, ?)",
        [session_id, role, content, meta_json],
    )
    msg_id = cur.lastrowid
    if msg_id is None:
        cur.close()
        conn.rollback()
        raise RuntimeError("Message INSERT did not return an auto-increment ID")
    conn.commit()
    cur.close()
    return msg_id


def record_tool_call(
    conn: pycubrid.connection.Connection,
    session_id: int,
    tool_name: str,
    arguments: dict,
    result: dict | None = None,
    status: str = "completed",
    duration_ms: int = 0,
) -> int:
    """Record a tool invocation with its arguments and result."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO cookbook_agent_tool_calls "
        "(session_id, tool_name, arguments, result, status, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            session_id,
            tool_name,
            json.dumps(arguments),
            json.dumps(result) if result else None,
            status,
            duration_ms,
        ],
    )
    call_id = cur.lastrowid
    if call_id is None:
        cur.close()
        conn.rollback()
        raise RuntimeError("Tool-call INSERT did not return an auto-increment ID")
    conn.commit()
    cur.close()
    return call_id


def get_conversation(
    conn: pycubrid.connection.Connection,
    session_id: int,
) -> list[dict]:
    """Retrieve the full conversation for a session."""
    cur = conn.cursor()
    cur.execute(
        "SELECT message_role, content, metadata, created_at "
        "FROM cookbook_agent_messages WHERE session_id = ? ORDER BY id",
        [session_id],
    )
    messages = []
    for row in cur:
        msg = {
            "role": row[0],
            "content": row[1],
            "metadata": json.loads(row[2]) if row[2] else None,
            "timestamp": str(row[3]),
        }
        messages.append(msg)
    cur.close()
    return messages


def main() -> None:
    with closing(pycubrid.connect(**DB_CONFIG)) as conn:
        setup_schema(conn)

        delete_session(conn, DEMO_SESSION_KEY)  # rerunnable: drop the previous run's session
        session_id = create_session(conn, DEMO_SESSION_KEY, tags=["demo", "analytics"])
        print(f"Session created: {session_id}")

        add_message(conn, session_id, "user", "What are the top 5 products?")
        add_message(
            conn,
            session_id,
            "assistant",
            "I'll query the products table for you.",
            metadata={"confidence": 0.95, "model": "demo"},
        )
        record_tool_call(
            conn,
            session_id,
            "execute_query",
            arguments={"sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 5"},
            result={"rows": 5, "truncated": False},
            duration_ms=42,
        )
        add_message(conn, session_id, "tool", "Query returned 5 rows")

        history = get_conversation(conn, session_id)
        print(f"Conversation ({len(history)} messages):")
        for msg in history:
            print(f"  [{msg['role']}] {msg['content']}")

        # Verify JSON metadata round-trip
        cur = conn.cursor()
        cur.execute(
            "SELECT metadata FROM cookbook_agent_messages WHERE session_id = ? AND message_role = 'assistant'",
            [session_id],
        )
        row = cur.fetchone()
        meta = json.loads(row[0]) if row and row[0] else {}
        print(f"Assistant metadata: {meta}")
        assert meta["confidence"] == 0.95

        cur.close()
        print("✓ Agent state management working")


if __name__ == "__main__":
    main()
