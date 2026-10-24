from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from urllib.parse import unquote, urlparse

import pycubrid
import pytest
from sqlalchemy.engine import make_url

CUBRID_TEST_URL = os.getenv("CUBRID_TEST_URL")
# Under the live gate (`make verify-ai-agent`, `make verify`) a missing URL fails instead of skipping.
LIVE_GATE = os.getenv("CUBRID_LIVE_GATE") == "1"
pytestmark = pytest.mark.skipif(
    not CUBRID_TEST_URL and not LIVE_GATE,
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
        if LIVE_GATE:
            pytest.fail("CUBRID_LIVE_GATE=1 requires CUBRID_TEST_URL; live tests must not skip")
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


REPO_ROOT = Path(__file__).resolve().parents[3]
RECIPE_ROOT = REPO_ROOT / "templates/ai-agent"
AGENT_STATE_TABLES = (
    "cookbook_agent_tool_calls",
    "cookbook_agent_messages",
    "cookbook_agent_sessions",
)
RECIPE_TABLES = {
    "01_agent_state.py": AGENT_STATE_TABLES,
    # 02 creates no tables; its read-only check targets a sentinel agent-state table.
    "02_mcp_toolchain.py": AGENT_STATE_TABLES,
    "03_rag_metadata.py": (
        "cookbook_rag_chunks",
        "cookbook_rag_retrieval_log",
        "cookbook_rag_documents",
    ),
    "04_agent_loop.py": (*AGENT_STATE_TABLES, "cookbook_agent_products"),
    "05_chatbot_backend.py": (
        "cookbook_chat_messages",
        "cookbook_chat_conversations",
        "cookbook_chat_users",
    ),
}
# A reader's rows that look like demonstration data (a generic session key, the
# username "alice", a document with a sample source URL but no recipe marker):
# (insert, count, delete) statements.
UNRELATED_ROWS = {
    "01_agent_state.py": (
        "INSERT INTO cookbook_agent_sessions (session_key, agent_name) VALUES ('demo-001', 'reader')",
        "SELECT COUNT(*) FROM cookbook_agent_sessions WHERE session_key = 'demo-001'",
        "DELETE FROM cookbook_agent_sessions WHERE session_key = 'demo-001'",
    ),
    "03_rag_metadata.py": (
        "INSERT INTO cookbook_rag_documents (title, source, content, metadata) VALUES ('Reader notes', "
        "'https://github.com/cubrid-lab/pycubrid', 'Reader notes', '{\"author\": \"reader\"}')",
        "SELECT COUNT(*) FROM cookbook_rag_documents WHERE title = 'Reader notes'",
        "DELETE FROM cookbook_rag_documents WHERE title = 'Reader notes'",
    ),
    "04_agent_loop.py": (
        "INSERT INTO cookbook_agent_sessions (session_key, agent_name) VALUES ('agent-loop-demo', 'reader')",
        "SELECT COUNT(*) FROM cookbook_agent_sessions WHERE session_key = 'agent-loop-demo'",
        "DELETE FROM cookbook_agent_sessions WHERE session_key = 'agent-loop-demo'",
    ),
    "05_chatbot_backend.py": (
        "INSERT INTO cookbook_chat_users (username, display_name, preferences) "
        "VALUES ('alice', 'Reader Alice', '{}')",
        "SELECT COUNT(*) FROM cookbook_chat_users WHERE username = 'alice'",
        "DELETE FROM cookbook_chat_users WHERE username = 'alice'",
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


AI_AGENT_RECIPES = [RECIPE_ROOT / name for name in RECIPE_TABLES]


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


def load_recipe(path):
    """Import a recipe file in-process (after the fixture has set its env vars)."""
    spec = importlib.util.spec_from_file_location(f"live_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------
# Independent database reads of what each recipe persisted
# ----------------------------------------------------------------
#
# Each reader returns (state, owned_ids). The state leaves out auto-increment IDs
# and timestamps, and resolves foreign keys through joins on the recipe's fixed
# key, so it is identical on every run. owned_ids are the recipe's root-row IDs,
# which a rerun must replace rather than reuse or duplicate.


def fetch(cursor, sql, params=()):
    cursor.execute(sql, list(params))
    return [tuple(row) for row in cursor.fetchall()]


def from_json(text):
    return json.loads(text) if text else None


def table_rows(cursor, tables):
    return {table: fetch(cursor, f"SELECT COUNT(*) FROM {table}")[0][0] for table in tables}


def agent_session_state(cursor, session_key):
    sessions = fetch(
        cursor,
        "SELECT id, agent_name, status FROM cookbook_agent_sessions WHERE session_key = ?",
        [session_key],
    )
    tags = fetch(
        cursor,
        "SELECT t.tag FROM cookbook_agent_sessions s, TABLE(s.tags) AS t(tag) "
        "WHERE s.session_key = ? ORDER BY 1",
        [session_key],
    )
    messages = fetch(
        cursor,
        "SELECT m.message_role, m.content, m.metadata FROM cookbook_agent_messages m "
        "JOIN cookbook_agent_sessions s ON m.session_id = s.id "
        "WHERE s.session_key = ? ORDER BY m.id",
        [session_key],
    )
    calls = fetch(
        cursor,
        "SELECT c.tool_name, c.arguments, c.result, c.status, c.duration_ms "
        "FROM cookbook_agent_tool_calls c JOIN cookbook_agent_sessions s ON c.session_id = s.id "
        "WHERE s.session_key = ? ORDER BY c.id",
        [session_key],
    )
    state = {
        "sessions": [(name, status) for _, name, status in sessions],
        "tags": [tag for (tag,) in tags],
        "messages": [(role, content, from_json(meta)) for role, content, meta in messages],
        "tool_calls": [
            (name, from_json(args), from_json(result), status, duration)
            for name, args, result, status, duration in calls
        ],
    }
    return state, [row[0] for row in sessions]


def agent_state_state(cursor):
    state, ids = agent_session_state(cursor, "cookbook-agent-state-demo")
    state["table_rows"] = table_rows(cursor, AGENT_STATE_TABLES)
    return state, ids


# The table list and timings depend on the database and the clock, not the recipe.
TABLE_LIST = re.compile(r"Found \d+ tables: .*", re.DOTALL)


def mask_tables(text):
    return TABLE_LIST.sub("Found <n> tables: <names>", text)


def agent_loop_state(cursor):
    state, ids = agent_session_state(cursor, "cookbook-agent-loop-demo")
    state["messages"] = [(role, mask_tables(text), meta) for role, text, meta in state["messages"]]
    state["tool_calls"] = [
        (name, args, {"summary": mask_tables(result["summary"])}, status, duration >= 0)
        for name, args, result, status, duration in state["tool_calls"]
    ]
    state["products"] = [
        (item_id, name, str(price))
        for item_id, name, price in fetch(
            cursor, "SELECT id, item_name, price FROM cookbook_agent_products ORDER BY id"
        )
    ]
    state["table_rows"] = table_rows(cursor, RECIPE_TABLES["04_agent_loop.py"])
    return state, ids


RAG_MARKER = "cookbook-ai-agent-rag-demo"


def rag_state(cursor):
    owned = "JSON_UNQUOTE(JSON_EXTRACT(d.metadata, '$.recipe')) = ?"
    documents = fetch(
        cursor,
        "SELECT d.id, d.title, d.source, d.metadata, d.chunk_count FROM cookbook_rag_documents d "
        "WHERE " + owned + " ORDER BY d.id",
        [RAG_MARKER],
    )
    tags = fetch(
        cursor,
        "SELECT d.title, t.tag FROM cookbook_rag_documents d, TABLE(d.tags) AS t(tag) "
        "WHERE " + owned + " ORDER BY 1, 2",
        [RAG_MARKER],
    )
    chunks = fetch(
        cursor,
        "SELECT d.id, d.title, c.chunk_index, c.token_count, c.embedding_ref, "
        "CASE WHEN c.content = d.content THEN 1 ELSE 0 END "
        "FROM cookbook_rag_chunks c JOIN cookbook_rag_documents d ON c.document_id = d.id "
        "WHERE " + owned + " ORDER BY d.id, c.chunk_index",
        [RAG_MARKER],
    )
    titles = {doc_id: title for doc_id, title, *_ in documents}
    logs = fetch(
        cursor,
        "SELECT id, query_text, llm_response, relevance_scores "
        "FROM cookbook_rag_retrieval_log ORDER BY id DESC LIMIT 1",
    )
    latest = None
    if logs:
        log_id, query_text, response, scores = logs[0]
        retrieved = fetch(
            cursor,
            "SELECT r.doc_id FROM cookbook_rag_retrieval_log, TABLE(retrieved_doc_ids) AS r(doc_id) "
            "WHERE id = ?",
            [log_id],
        )
        latest = {
            "query_text": query_text,
            # Resolve the logged IDs to this run's documents; a stale ID would not resolve.
            "retrieved": [titles.get(doc_id, f"<missing {doc_id}>") for (doc_id,) in retrieved],
            "llm_response": response,
            "relevance_scores": from_json(scores),
        }
    state = {
        "documents": [
            (title, source, from_json(meta), chunk_count)
            for _, title, source, meta, chunk_count in documents
        ],
        "tags": tags,
        "chunks": [
            (title, index, tokens, ref == f"vecstore://doc-{doc_id}/chunk-{index}", bool(same))
            for doc_id, title, index, tokens, ref, same in chunks
        ],
        "latest_retrieval": latest,
        "table_rows": table_rows(cursor, RECIPE_TABLES["03_rag_metadata.py"]),
    }
    return state, list(titles)


def chatbot_state(cursor):
    username = "cookbook_demo_alice"
    users = fetch(
        cursor,
        "SELECT id, display_name, preferences FROM cookbook_chat_users WHERE username = ?",
        [username],
    )
    conversations = fetch(
        cursor,
        "SELECT c.title, c.status FROM cookbook_chat_conversations c "
        "JOIN cookbook_chat_users u ON c.user_id = u.id WHERE u.username = ? ORDER BY c.id",
        [username],
    )
    messages = fetch(
        cursor,
        "SELECT m.role, m.content, m.metadata, m.token_count FROM cookbook_chat_messages m "
        "JOIN cookbook_chat_conversations c ON m.conversation_id = c.id "
        "JOIN cookbook_chat_users u ON c.user_id = u.id WHERE u.username = ? ORDER BY m.id",
        [username],
    )
    state = {
        "users": [(name, from_json(prefs)) for _, name, prefs in users],
        "conversations": conversations,
        "messages": [
            (role, content, from_json(meta), tokens) for role, content, meta, tokens in messages
        ],
        "table_rows": table_rows(cursor, RECIPE_TABLES["05_chatbot_backend.py"]),
    }
    return state, [row[0] for row in users]


RECIPE_STATE = {
    "01_agent_state.py": agent_state_state,
    "03_rag_metadata.py": rag_state,
    "04_agent_loop.py": agent_loop_state,
    "05_chatbot_backend.py": chatbot_state,
}


def expected_state(recipe, runs=1):
    """What each recipe must leave in the database after `runs` consecutive runs."""
    if recipe == "01_agent_state.py":
        return {
            "sessions": [("data-assistant", "active")],
            "tags": ["analytics", "demo"],
            "messages": [
                ("user", "What are the top 5 products?", None),
                (
                    "assistant",
                    "I'll query the products table for you.",
                    {"confidence": 0.95, "model": "demo"},
                ),
                ("tool", "Query returned 5 rows", None),
            ],
            "tool_calls": [
                (
                    "execute_query",
                    {"sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 5"},
                    {"rows": 5, "truncated": False},
                    "completed",
                    42,
                )
            ],
            "table_rows": {
                "cookbook_agent_tool_calls": 1,
                "cookbook_agent_messages": 3,
                "cookbook_agent_sessions": 1,
            },
        }
    if recipe == "03_rag_metadata.py":
        pycubrid_doc = "CUBRID Python Driver Guide"
        return {
            "documents": [
                (
                    pycubrid_doc,
                    "https://github.com/cubrid-lab/pycubrid",
                    {
                        "author": "cubrid-lab",
                        "type": "documentation",
                        "version": "1.7",
                        "recipe": RAG_MARKER,
                    },
                    1,
                ),
                (
                    "SQLAlchemy CUBRID Dialect",
                    "https://github.com/cubrid-lab/sqlalchemy-cubrid",
                    {
                        "author": "cubrid-lab",
                        "type": "documentation",
                        "version": "1.7",
                        "recipe": RAG_MARKER,
                    },
                    1,
                ),
                (
                    "MCP Server for CUBRID",
                    "https://github.com/cubrid-lab/cubrid-mcp-server",
                    {
                        "author": "cubrid-lab",
                        "type": "tool",
                        "version": "0.4",
                        "recipe": RAG_MARKER,
                    },
                    1,
                ),
            ],
            "tags": [
                (pycubrid_doc, "driver"),
                (pycubrid_doc, "getting-started"),
                (pycubrid_doc, "python"),
                ("MCP Server for CUBRID", "ai"),
                ("MCP Server for CUBRID", "llm"),
                ("MCP Server for CUBRID", "mcp"),
                ("MCP Server for CUBRID", "safety"),
                ("SQLAlchemy CUBRID Dialect", "orm"),
                ("SQLAlchemy CUBRID Dialect", "python"),
                ("SQLAlchemy CUBRID Dialect", "sqlalchemy"),
            ],
            # (title, chunk_index, token_count, embedding_ref names this chunk, full text)
            "chunks": [
                (pycubrid_doc, 0, 25, True, True),
                ("SQLAlchemy CUBRID Dialect", 0, 18, True, True),
                ("MCP Server for CUBRID", 0, 21, True, True),
            ],
            "latest_retrieval": {
                "query_text": "How do I connect Python to CUBRID?",
                # Only this document's content contains "Python". LIKE follows the
                # column collation (case-sensitive under CUBRID's default utf8_bin);
                # no other sample content contains "python" in any case either.
                "retrieved": [pycubrid_doc],
                "llm_response": (
                    "Based on the retrieved documents, pycubrid is the pure Python "
                    "DB-API 2.0 driver for CUBRID. You can install it with "
                    "'pip install pycubrid' and connect using pycubrid.connect()."
                ),
                "relevance_scores": [0.92],
            },
            # The retrieval log is append-only: one row per run.
            "table_rows": {
                "cookbook_rag_chunks": 3,
                "cookbook_rag_retrieval_log": runs,
                "cookbook_rag_documents": 3,
            },
        }
    if recipe == "04_agent_loop.py":

        def turn(query, tool, plan, answer):
            return [
                ("user", query, None),
                ("assistant", f"Plan: {plan}", {"tool": tool, "reasoning": "heuristic"}),
                ("assistant", f"Based on the data: {answer}", None),
            ]

        # The recipe stores repr() of the driver's rows: this text depends on pycubrid
        # returning tuples and NUMERIC(10, 2) as Decimal with scale 2 (e.g. '45.00').
        top_products = (
            "Query returned 3 rows\n  ('Keyboard', Decimal('45.00'))"
            "\n  ('Notebook', Decimal('12.50'))\n  ('Pen', Decimal('2.00'))"
        )
        top_sql = "SELECT item_name, price FROM cookbook_agent_products ORDER BY price DESC LIMIT 5"
        return {
            "sessions": [("data-assistant", "active")],
            "tags": ["agent-loop"],
            "messages": [
                *turn(
                    "What tables are in this database?",
                    "all_table_names",
                    "list_tables → describe → answer",
                    "Found <n> tables: <names>",
                ),
                *turn(
                    "Show me the top products by price",
                    "execute_query",
                    "query → format → answer",
                    top_products,
                ),
                *turn(
                    "How are you doing?", "health_check", "health_check → answer", "Connection OK"
                ),
            ],
            # (tool, arguments, result, status, duration_ms >= 0)
            "tool_calls": [
                (
                    "all_table_names",
                    {},
                    {"summary": "Found <n> tables: <names>"},
                    "completed",
                    True,
                ),
                (
                    "execute_query",
                    {"sql": top_sql},
                    {"summary": top_products[:100]},
                    "completed",
                    True,
                ),
                ("health_check", {}, {"summary": "Connection OK"}, "completed", True),
            ],
            # str() of the driver's Decimal values, which keep NUMERIC(10, 2)'s scale.
            "products": [(1, "Notebook", "12.50"), (2, "Pen", "2.00"), (3, "Keyboard", "45.00")],
            "table_rows": {
                "cookbook_agent_tool_calls": 3,
                "cookbook_agent_messages": 9,
                "cookbook_agent_sessions": 1,
                "cookbook_agent_products": 3,
            },
        }
    if recipe == "05_chatbot_backend.py":
        exchanges = [
            ("user", "Hello! Can you help me analyze my data?", 8),
            ("assistant", "Of course! I'd be happy to help you analyze your CUBRID data.", 12),
            ("user", "What tables do I have?", 5),
            ("assistant", "You have tables for users, products, and orders.", 8),
        ]
        return {
            "users": [("Alice Kim", {"model": "gpt-4", "temperature": 0.7, "max_tokens": 2000})],
            "conversations": [("CUBRID + AI Demo", "active")],
            "messages": [
                (role, content, {"turn": turn, "source": "demo"}, tokens)
                for turn, (role, content, tokens) in enumerate(exchanges)
            ],
            "table_rows": {
                "cookbook_chat_messages": 4,
                "cookbook_chat_conversations": 1,
                "cookbook_chat_users": 1,
            },
        }
    raise KeyError(recipe)


def assert_state(actual, expected, label):
    """Fail with every mismatched key, its expected and its actual value."""
    keys = sorted(expected.keys() | actual.keys())
    diffs = [
        f"  {key}: expected {expected.get(key)!r}, got {actual.get(key)!r}"
        for key in keys
        if actual.get(key) != expected.get(key)
    ]
    assert not diffs, f"{label}: persisted state differs\n" + "\n".join(diffs)


def read_state(recipe):
    with live_connection() as conn, conn.cursor() as cursor:
        return RECIPE_STATE[recipe](cursor)


@pytest.mark.parametrize("app_path", AI_AGENT_RECIPES, ids=lambda path: path.name)
def test_ai_agent_recipes_runs_without_errors(app_path):
    """
    Test that each ai-agent recipe runs to completion without raising any
    exception against a live CUBRID database instance.

    A separate, bounded Python process executes each script's __main__ and
    releases all database sessions even if the script raises. Failures include
    both stdout and stderr so the live traceback remains visible. Afterwards an
    independent connection reads back what the recipe persisted.
    """
    output = run_recipe(app_path)
    if app_path.name == "02_mcp_toolchain.py":
        assert "Server: cubrid-mcp-server" in output
        assert "DROP TABLE rejected by read-only whitelist: ✓" in output
    if app_path.name == "05_chatbot_backend.py":
        # Each stored message carries its own turn number, not 0 for all (#328).
        turns = [line.split()[1] for line in output.splitlines() if line.startswith("  turn ")]
        assert turns == ["0", "1", "2", "3"]
    if app_path.name in RECIPE_STATE:
        state, _ = read_state(app_path.name)
        assert_state(state, expected_state(app_path.name), app_path.name)


@pytest.mark.parametrize("app_path", AI_AGENT_RECIPES, ids=lambda path: path.name)
def test_ai_agent_recipes_rerun_on_same_database(app_path):
    """
    Each recipe can run twice in a row without the tables being reset in
    between: fixed demonstration keys (session keys, the ``alice`` user) from
    the first run must not raise a unique-constraint violation on the second,
    and the second run leaves the same business state with fresh root rows.
    """
    first = run_recipe(app_path)
    first_ids = read_state(app_path.name)[1] if app_path.name in RECIPE_STATE else []
    unrelated = UNRELATED_ROWS.get(app_path.name)
    if unrelated:
        insert_sql, _, _ = unrelated
        with live_connection() as conn, conn.cursor() as cursor:
            cursor.execute(insert_sql)
            conn.commit()
    second = run_recipe(app_path)
    assert first.count("\n") == second.count("\n")
    if unrelated:
        # The rerun cleanup removes only recipe-owned rows, not a reader's own data.
        _, check_sql, delete_sql = unrelated
        with live_connection() as conn, conn.cursor() as cursor:
            cursor.execute(check_sql)
            assert cursor.fetchone()[0] == 1
            cursor.execute(delete_sql)
            conn.commit()
    if app_path.name in RECIPE_STATE:
        state, second_ids = read_state(app_path.name)
        assert_state(state, expected_state(app_path.name, runs=2), app_path.name)
        # The previous run's fixed-key rows were deleted and recreated, not reused.
        assert len(second_ids) == len(first_ids) > 0
        assert not set(first_ids) & set(second_ids)


MCP_SENTINEL_KEY = "cookbook-mcp-readonly-sentinel"


def mcp_target_state():
    """The DROP target's existence and rows, read without the MCP server."""
    with live_connection() as conn, conn.cursor() as cursor:
        exists = fetch(
            cursor,
            "SELECT COUNT(*) FROM db_class WHERE class_name = ? AND is_system_class = 'NO'",
            ["cookbook_agent_sessions"],
        )[0][0]
        keys = fetch(cursor, "SELECT session_key FROM cookbook_agent_sessions") if exists else []
    return {"table_exists": exists == 1, "session_keys": keys}


def mcp_tool_result(mcp, proc, request_id, name, arguments):
    reply = mcp.send_mcp_request(
        proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    return reply["result"]


def structured(result):
    """A tool's structured payload; older servers send it only as JSON text.

    The text form of a list result is the bare JSON list, not {"result": [...]}.
    """
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize(
    "app_path", [RECIPE_ROOT / "02_mcp_toolchain.py"], ids=lambda path: path.name
)
def test_mcp_toolchain_protocol_and_read_only_state(app_path):
    """
    The MCP recipe's handshake, tool listing and table list match the database,
    and its rejected DROP TABLE leaves the target table and its rows unchanged.
    """
    agent_state = load_recipe(RECIPE_ROOT / "01_agent_state.py")
    with live_connection() as conn:
        agent_state.setup_schema(conn)
        agent_state.create_session(conn, MCP_SENTINEL_KEY)
    before = mcp_target_state()
    assert before == {"table_exists": True, "session_keys": [(MCP_SENTINEL_KEY,)]}

    output = run_recipe(app_path)
    assert "Server: cubrid-mcp-server" in output
    assert "DROP TABLE rejected by read-only whitelist: ✓" in output
    assert mcp_target_state() == before

    with live_connection() as conn, conn.cursor() as cursor:
        user_tables = fetch(
            cursor,
            "SELECT owner_name, class_name FROM db_class "
            "WHERE class_type = 'CLASS' AND is_system_class = 'NO'",
        )
    # cubrid_mcp_server.server._user_tables / _Table.display: "owner.table" with the
    # owner lowercased on 11.2+ (two owners may share a table name), else "table".
    qualified_tables = sorted(f"{owner.lower()}.{name}" for owner, name in user_tables)
    reported = re.search(r"Tables in database \((\d+)\)", output)
    assert reported and int(reported.group(1)) == len(qualified_tables), output

    smoke = load_recipe(REPO_ROOT / "scripts/mcp_smoke.py")
    mcp = load_recipe(app_path)
    proc = mcp.start_mcp_server()
    try:
        init = mcp.send_mcp_request(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "cookbook-ai-agent-test", "version": "1.0.0"},
                },
            },
        )["result"]
        assert init["serverInfo"]["name"] == "cubrid-mcp-server"
        assert init["protocolVersion"] and "tools" in init["capabilities"]
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        proc.stdin.write("\n")
        proc.stdin.flush()

        listed = mcp.send_mcp_request(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert smoke.EXPECTED <= tool_names

        tables = mcp_tool_result(mcp, proc, 3, "all_table_names", {})
        assert not tables.get("isError"), tables
        payload = structured(tables)
        # structuredContent wraps the list in {"result": [...]}; the text form is the bare list.
        names = payload["result"] if isinstance(payload, dict) else payload
        assert isinstance(names, list) and all(isinstance(name, str) for name in names)
        # A server release without owner qualification lists bare names; a list (not a
        # set) still keeps same-named tables of different owners apart.
        expected_names = (
            qualified_tables
            if any("." in name for name in names)
            else sorted(name for _, name in user_tables)
        )
        assert sorted(names) == expected_names
        assert len(names) == len(qualified_tables)

        count = mcp_tool_result(
            mcp, proc, 4, "execute_query", {"sql": "SELECT COUNT(*) FROM cookbook_agent_sessions"}
        )
        assert not count.get("isError"), count
        assert structured(count)["rows"] == [[1]]

        drop = mcp_tool_result(
            mcp, proc, 5, "execute_query", {"sql": "DROP TABLE cookbook_agent_sessions"}
        )
        rejection = " ".join(block.get("text", "") for block in drop.get("content", []))
        assert drop.get("isError") and "read-only" in rejection.lower(), drop
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    assert mcp_target_state() == before
