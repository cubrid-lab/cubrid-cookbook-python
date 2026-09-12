"""Agent state management — store sessions, messages, and tool calls.

CUBRID acts as the persistent state store for an AI agent:
- `agent_sessions`: one row per conversation thread
- `agent_messages`: individual turns (user / assistant / tool)
- `agent_tool_calls`: structured records of every tool invocation

Demonstrates JSON columns for LLM I/O, SET for tagging,
and AUTO_INCREMENT for ordering.
"""

from __future__ import annotations

import json

import pycubrid

# ----------------------------------------------------------------
# Schema setup
# ----------------------------------------------------------------

DDL = [
    """
    CREATE TABLE IF NOT EXISTS agent_sessions (
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
    CREATE TABLE IF NOT EXISTS agent_messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        content TEXT,
        metadata JSON,
        created_at DATETIME DEFAULT SYS_DATETIME,
        FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_tool_calls (
        id INT AUTO_INCREMENT PRIMARY KEY,
        session_id INT NOT NULL,
        tool_name VARCHAR(100) NOT NULL,
        arguments JSON,
        result JSON,
        status VARCHAR(20) DEFAULT 'pending',
        duration_ms INT,
        created_at DATETIME DEFAULT SYS_DATETIME,
        FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
    )
    """,
]


def setup_schema(conn: pycubrid.connection.Connection) -> None:
    cur = conn.cursor()
    for ddl in DDL:
        cur.execute(ddl)
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
    tag_set = "{" + ", ".join(f"'{t}'" for t in (tags or [])) + "}"
    cur.execute(
        f"INSERT INTO agent_sessions (session_key, agent_name, tags) VALUES (?, ?, {tag_set})",
        [session_key, agent_name],
    )
    conn.commit()
    session_id = int(conn.get_last_insert_id())
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
        "INSERT INTO agent_messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
        [session_id, role, content, meta_json],
    )
    conn.commit()
    msg_id = int(conn.get_last_insert_id())
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
        "INSERT INTO agent_tool_calls "
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
    conn.commit()
    call_id = int(conn.get_last_insert_id())
    cur.close()
    return call_id


def get_conversation(
    conn: pycubrid.connection.Connection,
    session_id: int,
) -> list[dict]:
    """Retrieve the full conversation for a session."""
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content, metadata, created_at "
        "FROM agent_messages WHERE session_id = ? ORDER BY id",
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
    conn = pycubrid.connect(database="testdb")
    setup_schema(conn)

    session_id = create_session(conn, "demo-001", tags=["demo", "analytics"])
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
        "SELECT metadata FROM agent_messages WHERE session_id = ? AND role = 'assistant'",
        [session_id],
    )
    row = cur.fetchone()
    meta = json.loads(row[0]) if row and row[0] else {}
    print(f"Assistant metadata: {meta}")
    assert meta["confidence"] == 0.95

    cur.close()
    conn.close()
    print("✓ Agent state management working")


if __name__ == "__main__":
    main()
