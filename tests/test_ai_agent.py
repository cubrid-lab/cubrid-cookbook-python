from __future__ import annotations
import os
from pathlib import Path
import signal
import subprocess
import sys
from urllib.parse import unquote, urlparse

import pycubrid
import pytest
from sqlalchemy.engine import make_url

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")
pytestmark = pytest.mark.skipif(
    not CUBRID_TEST_URL,
    reason="CUBRID_live instance URL (CUBRID_TEST_URL) not provided. Skipping live DB tests.",
)


@pytest.fixture(autouse=True)
def setup_database_url(monkeypatch, app_path):
    """
    Ensure ai-agent recipes connect to the live CUBRID test instance.

    Unlike the dashboard recipes, the ai-agent recipes don't all read a
    single DATABASE_URL - 01/03/04 call pycubrid.connect() directly with
    discrete CUBRID_HOST/CUBRID_PORT/CUBRID_USER/CUBRID_PASSWORD/
    CUBRID_DATABASE env vars (the same names 02_mcp_toolchain.py already
    used), and 05 uses a SQLAlchemy DATABASE_URL like the dashboard
    recipes do. CUBRID_TEST_URL is parsed once here and fans out into
    both shapes so a single env var still drives every recipe.
    """
    if not CUBRID_TEST_URL:
        return

    parsed = urlparse(CUBRID_TEST_URL)
    config = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 33000,
        "user": unquote(parsed.username or "dba"),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/")) or "testdb",
    }
    sqlalchemy_url = make_url(CUBRID_TEST_URL).set(drivername="cubrid+pycubrid")
    monkeypatch.setenv("CUBRID_URL", CUBRID_TEST_URL)
    monkeypatch.setenv("DATABASE_URL", sqlalchemy_url.render_as_string(hide_password=False))
    monkeypatch.setenv("CUBRID_MCP_READONLY", "1")
    for key, value in config.items():
        monkeypatch.setenv(f"CUBRID_{key.upper()}", str(value))

    # Only these recipes' tables are reset; children precede foreign-key parents.
    # Use a dedicated test database: these scripts use fixed demonstration keys.
    tables = RECIPE_TABLES[app_path.name]

    def drop_recipe_tables():
        with pycubrid.connect(**config, connect_timeout=10, read_timeout=15) as conn:
            with conn.cursor() as cursor:
                for table in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {table}")

    drop_recipe_tables()
    try:
        yield
    finally:
        drop_recipe_tables()


REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE_TABLES = {
    "01_agent_state.py": ("agent_tool_calls", "agent_messages", "agent_sessions"),
    "02_mcp_toolchain.py": (),
    "03_rag_metadata.py": ("rag_chunks", "rag_retrieval_log", "rag_documents"),
    "04_agent_loop.py": (
        "agent_tool_calls",
        "agent_messages",
        "agent_sessions",
        "cookbook_agent_products",
    ),
    "05_chatbot_backend.py": ("chat_messages", "chat_conversations", "chat_users"),
}
# A reader's rows that look like demonstration data (a generic session key, the
# username "alice", a document with a sample source URL but no recipe marker).
UNRELATED_ROWS = {
    "01_agent_state.py": (
        "INSERT INTO agent_sessions (session_key, agent_name) VALUES ('demo-001', 'reader')",
        "SELECT COUNT(*) FROM agent_sessions WHERE session_key = 'demo-001'",
    ),
    "03_rag_metadata.py": (
        "INSERT INTO rag_documents (title, source, content, metadata) VALUES ('Reader notes', "
        "'https://github.com/cubrid-lab/pycubrid', 'Reader notes', '{\"author\": \"reader\"}')",
        "SELECT COUNT(*) FROM rag_documents WHERE title = 'Reader notes'",
    ),
    "04_agent_loop.py": (
        "INSERT INTO agent_sessions (session_key, agent_name) VALUES ('agent-loop-demo', 'reader')",
        "SELECT COUNT(*) FROM agent_sessions WHERE session_key = 'agent-loop-demo'",
    ),
    "05_chatbot_backend.py": (
        "INSERT INTO chat_users (username, display_name, preferences) "
        "VALUES ('alice', 'Reader Alice', '{}')",
        "SELECT COUNT(*) FROM chat_users WHERE username = 'alice'",
    ),
}


def live_connection():
    parsed = urlparse(CUBRID_TEST_URL)
    return pycubrid.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 33000,
        user=unquote(parsed.username or "dba"),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.lstrip("/")) or "testdb",
        connect_timeout=10,
        read_timeout=15,
    )


AI_AGENT_RECIPES = [REPO_ROOT / "templates/ai-agent" / name for name in RECIPE_TABLES]


def run_recipe(app_path):
    """Run one recipe's __main__ in a bounded process group and return its stdout."""
    with subprocess.Popen(
        [sys.executable, str(app_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            output, errors = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            # Terminate only this test's process group, including its MCP child.
            os.killpg(process.pid, signal.SIGKILL)
            output, errors = process.communicate()
            pytest.fail(f"Recipe exceeded 60 seconds: {app_path.name}\n{output}\n{errors}")
    assert process.returncode == 0, output + errors
    assert "✓" in output and "working" in output
    assert "Query failed:" not in output
    return output


@pytest.mark.parametrize("app_path", AI_AGENT_RECIPES, ids=lambda path: path.name)
def test_ai_agent_recipes_runs_without_errors(app_path):
    """
    Test that each ai-agent recipe runs to completion without raising any
    exception against a live CUBRID database instance.

    A separate, bounded Python process executes each script's __main__ and
    releases all database sessions even if the script raises. Failures include
    both stdout and stderr so the live traceback remains visible.
    """
    output = run_recipe(app_path)
    if app_path.name == "02_mcp_toolchain.py":
        assert "Server: cubrid-mcp-server" in output
        assert "DROP TABLE rejected by read-only whitelist: ✓" in output


@pytest.mark.parametrize("app_path", AI_AGENT_RECIPES, ids=lambda path: path.name)
def test_ai_agent_recipes_rerun_on_same_database(app_path):
    """
    Each recipe can run twice in a row without the tables being reset in
    between: fixed demonstration keys (session keys, the ``alice`` user) from
    the first run must not raise a unique-constraint violation on the second.
    """
    first = run_recipe(app_path)
    unrelated = UNRELATED_ROWS.get(app_path.name)
    if unrelated:
        insert_sql, check_sql = unrelated
        with live_connection() as conn, conn.cursor() as cursor:
            cursor.execute(insert_sql)
            conn.commit()
    second = run_recipe(app_path)
    assert first.count("\n") == second.count("\n")
    if unrelated:
        # The rerun cleanup removes only recipe-owned rows, not a reader's own data.
        with live_connection() as conn, conn.cursor() as cursor:
            cursor.execute(check_sql)
            assert cursor.fetchone()[0] == 1
