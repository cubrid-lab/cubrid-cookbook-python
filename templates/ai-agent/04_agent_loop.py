"""Agent loop — a minimal query → think → act → observe cycle.

Demonstrates how CUBRID serves as the backbone for an agentic workflow:
1. Agent receives a user query
2. Plans tool calls (recorded in agent_tool_calls)
3. Executes against CUBRID via the MCP read-only whitelist
4. Observes results and decides next action
5. Synthesizes a response (all turns stored in agent_messages)
"""

from __future__ import annotations

import time

import pycubrid

# Reuse the schema from 01_agent_state.py
from importlib.util import spec_from_file_location, module_from_spec

_spec = spec_from_file_location("agent_state", "templates/ai-agent/01_agent_state.py")
_agent_state = module_from_spec(_spec)
_spec.loader.exec_module(_agent_state)


class SimpleDataAgent:
    """A minimal agentic data assistant backed by CUBRID.

    This is intentionally simple — it demonstrates the STATE pattern,
    not the AI logic. Replace the heuristic responses with actual
    LLM calls (OpenAI, Anthropic, etc.) for a production agent.
    """

    def __init__(self, conn: pycubrid.connection.Connection, session_key: str):
        self.conn = conn
        self.session_id = _agent_state.create_session(conn, session_key, tags=["agent-loop"])

    def think(self, user_query: str) -> str:
        """Simulate the 'thinking' step — plan what tools to call."""
        _agent_state.add_message(self.conn, self.session_id, "user", user_query)

        # Simple heuristic planning (replace with LLM)
        if "table" in user_query.lower():
            plan = "list_tables → describe → answer"
            tool = "all_table_names"
            args = {}
        elif "product" in user_query.lower() or "price" in user_query.lower():
            plan = "query → format → answer"
            tool = "execute_query"
            args = {"sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 5"}
        else:
            plan = "health_check → answer"
            tool = "health_check"
            args = {}

        _agent_state.add_message(
            self.conn,
            self.session_id,
            "assistant",
            f"Plan: {plan}",
            metadata={"tool": tool, "reasoning": "heuristic"},
        )
        return tool, args

    def act(self, tool: str, args: dict) -> str:
        """Execute the planned tool call against CUBRID."""
        start = time.perf_counter()
        cur = self.conn.cursor()

        if tool == "all_table_names":
            cur.execute(
                "SELECT class_name FROM db_class "
                "WHERE class_type = 'CLASS' AND is_system_class = 'NO'"
            )
            tables = [row[0] for row in cur]
            result = f"Found {len(tables)} tables: {', '.join(tables[:5])}"
        elif tool == "execute_query":
            try:
                cur.execute(args.get("sql", "SELECT 1"))
                rows = cur.fetchall()
                result = f"Query returned {len(rows)} rows"
                for row in rows[:3]:
                    result += f"\n  {row}"
            except pycubrid.Error as e:
                result = f"Query failed: {e.msg}"
        else:
            result = "Connection OK"

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        cur.close()

        _agent_state.record_tool_call(
            self.conn,
            self.session_id,
            tool,
            arguments=args,
            result={"summary": result[:100]},
            duration_ms=elapsed_ms,
        )
        return result

    def observe_and_respond(self, tool_result: str) -> str:
        """Synthesize a response from the tool output."""
        response = f"Based on the data: {tool_result}"
        _agent_state.add_message(self.conn, self.session_id, "assistant", response)
        return response

    def run(self, user_query: str) -> str:
        """One complete agent loop."""
        tool, args = self.think(user_query)
        result = self.act(tool, args)
        return self.observe_and_respond(result)

    def get_transcript(self) -> list[dict]:
        return _agent_state.get_conversation(self.conn, self.session_id)


def main() -> None:
    conn = pycubrid.connect(database="testdb")
    _agent_state.setup_schema(conn)

    agent = SimpleDataAgent(conn, "agent-loop-demo")

    # Agent loop: multiple queries
    print("Agent loop demo")
    print("=" * 50)

    queries = [
        "What tables are in this database?",
        "Show me the top products by price",
        "How are you doing?",
    ]

    for query in queries:
        print(f"\n[User] {query}")
        response = agent.run(query)
        print(f"[Agent] {response}")

    # Show full conversation transcript
    transcript = agent.get_transcript()
    print(f"\n{'=' * 50}")
    print(f"Full transcript ({len(transcript)} messages):")
    for msg in transcript:
        meta = f" ({msg['metadata']})" if msg["metadata"] else ""
        print(f"  [{msg['role']}]{meta} {msg['content'][:70]}")

    # Show tool call history with timing
    cur = conn.cursor()
    cur.execute(
        "SELECT tool_name, status, duration_ms FROM agent_tool_calls "
        "WHERE session_id = ? ORDER BY id",
        [agent.session_id],
    )
    calls = cur.fetchall()
    print(f"\nTool calls ({len(calls)}):")
    for name, status, duration in calls:
        print(f"  {name}: {status} ({duration}ms)")

    cur.close()
    conn.close()
    print("\n✓ Agent loop working")


if __name__ == "__main__":
    main()
