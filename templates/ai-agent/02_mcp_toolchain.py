"""MCP tool chain — programmatically call cubrid-mcp-server tools.

Shows how to use the MCP server as a library (without Claude Desktop)
to let an AI agent safely query CUBRID through the read-only whitelist.
"""

from __future__ import annotations

import json
import os
import selectors
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
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=15):
            raise RuntimeError("MCP server did not respond within 15 seconds")
    response_line = proc.stdout.readline()
    if not response_line:
        raise RuntimeError("MCP server closed its output without a response")
    response = json.loads(response_line)
    if response.get("id") != request["id"]:
        raise RuntimeError(f"Unexpected MCP response ID: {response}")
    if "error" in response:
        raise RuntimeError(f"MCP request failed: {response['error']}")
    if "result" not in response:
        raise RuntimeError(f"MCP response has no result: {response}")
    return response


def start_mcp_server() -> subprocess.Popen:
    """Launch cubrid-mcp-server as a subprocess speaking MCP over stdio."""
    env = {**os.environ, **DB_CONFIG, "CUBRID_MCP_READONLY": "1"}
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
        server_name = init_response["result"]["serverInfo"]["name"]
        print(f"  Server: {server_name}")
        # Complete the MCP initialization handshake before calling tools.
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        proc.stdin.flush()

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
        if not {"all_table_names", "execute_query"}.issubset({tool["name"] for tool in tools}):
            raise RuntimeError("MCP server is missing the tools used by this example")
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
        query_result = query_response["result"]
        if query_result.get("isError"):
            raise RuntimeError(f"MCP table query failed: {query_result}")
        table_names = query_result.get("structuredContent", {}).get("result")
        if table_names is None:
            content = query_result.get("content", [])
            if not content:
                raise RuntimeError("MCP table query returned no list result")
            table_names = json.loads(content[0]["text"])
        if not isinstance(table_names, list) or not all(
            isinstance(name, str) for name in table_names
        ):
            raise RuntimeError(f"MCP table query did not return a list of names: {table_names}")
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
                    "arguments": {"sql": "DROP TABLE cookbook_agent_sessions"},
                },
            },
        )
        write_result = write_response["result"]
        rejection_text = " ".join(
            block.get("text", "") for block in write_result.get("content", [])
        )
        if not write_result.get("isError") or "read-only" not in rejection_text.lower():
            raise RuntimeError(
                f"MCP server did not reject the write in read-only mode: {write_result}"
            )
        print("  DROP TABLE rejected by read-only whitelist: ✓")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    print("✓ MCP tool chain working")


if __name__ == "__main__":
    main()
