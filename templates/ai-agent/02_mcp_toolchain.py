"""MCP tool chain — programmatically call cubrid-mcp-server tools.

Shows how to use the MCP server as a library (without Claude Desktop)
to let an AI agent safely query CUBRID through the read-only whitelist.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

DB_CONFIG = {
    "CUBRID_HOST": os.environ.get("CUBRID_HOST", "localhost"),
    "CUBRID_PORT": os.environ.get("CUBRID_PORT", "33000"),
    "CUBRID_USER": os.environ.get("CUBRID_USER", "dba"),
    "CUBRID_PASSWORD": os.environ.get("CUBRID_PASSWORD", ""),
    "CUBRID_DATABASE": os.environ.get("CUBRID_DATABASE", "testdb"),
}


def send_mcp_request(proc: subprocess.Popen, request: dict) -> dict:
    """Send a JSON-RPC request to the MCP server and read the response."""
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    response_line = proc.stdout.readline()
    return json.loads(response_line) if response_line else {}


def start_mcp_server() -> subprocess.Popen:
    """Launch cubrid-mcp-server as a subprocess speaking MCP over stdio."""
    env = {**os.environ, **DB_CONFIG}
    proc = subprocess.Popen(
        [sys.executable, "-m", "cubrid_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return proc


def main() -> None:
    print("MCP tool chain demo — querying CUBRID via MCP protocol")
    print(
        f"  Target: {DB_CONFIG['CUBRID_HOST']}:{DB_CONFIG['CUBRID_PORT']}/{DB_CONFIG['CUBRID_DATABASE']}"
    )

    proc = start_mcp_server()

    try:
        # 1. Initialize the MCP session
        init_response = send_mcp_request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agent-demo", "version": "1.0.0"},
                },
            },
        )
        print(
            f"  Server: {init_response.get('result', {}).get('serverInfo', {}).get('name', 'unknown')}"
        )

        # 2. List available tools
        tools_response = send_mcp_request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            },
        )
        tools = tools_response.get("result", {}).get("tools", [])
        print(f"  Available tools ({len(tools)}):")
        for tool in tools:
            desc = tool.get("description", "")[:60]
            print(f"    - {tool['name']}: {desc}...")

        # 3. Call a read-only tool
        query_response = send_mcp_request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "all_table_names",
                    "arguments": {},
                },
            },
        )
        content = query_response.get("result", {}).get("content", [])
        tables_text = content[0]["text"] if content else "no result"
        table_names = [t.strip() for t in tables_text.split(",")]
        print(f"  Tables in database ({len(table_names)}): {table_names[:5]}...")

        # 4. Try a write (should be rejected by the read-only whitelist)
        write_response = send_mcp_request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "execute_query",
                    "arguments": {"sql": "DROP TABLE agent_sessions"},
                },
            },
        )
        is_error = write_response.get("result", {}).get("isError", False)
        print(f"  DROP TABLE rejected by read-only whitelist: {'✓' if is_error else '✗'}")

    finally:
        proc.terminate()
        proc.wait()

    print("✓ MCP tool chain working")


if __name__ == "__main__":
    main()
