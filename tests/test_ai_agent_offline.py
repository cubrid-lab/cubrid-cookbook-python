from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

RECIPE_ROOT = Path(__file__).resolve().parents[1] / "templates/ai-agent"


def load_recipe(name, monkeypatch=None):
    spec = importlib.util.spec_from_file_location("agent_recipe", RECIPE_ROOT / name)
    module = importlib.util.module_from_spec(spec)
    if monkeypatch is not None:
        # SQLAlchemy resolves deferred annotations through the defining module.
        monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def load_live_suite():
    spec = importlib.util.spec_from_file_location(
        "agent_live_suite", RECIPE_ROOT.parents[1] / "tests/test_ai_agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INSERT_CASES = [
    ("01_agent_state.py", "create_session", ("session",)),
    ("01_agent_state.py", "add_message", (1, "user", "Hello")),
    ("01_agent_state.py", "record_tool_call", (1, "query", {})),
    (
        "03_rag_metadata.py",
        "ingest_document",
        (
            {
                "title": "Demo",
                "source": "demo",
                "content": "Hello",
                "tags": ["demo"],
                "metadata": {},
            },
        ),
    ),
]


@pytest.mark.parametrize("recipe,operation,arguments", INSERT_CASES)
def test_insert_captures_cursor_id_before_commit(recipe, operation, arguments):
    module = load_recipe(recipe)
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.lastrowid = 17
    conn.commit.side_effect = lambda: setattr(cursor, "lastrowid", None)

    assert getattr(module, operation)(conn, *arguments) == 17
    conn.get_last_insert_id.assert_not_called()
    cursor.close.assert_called_once()


@pytest.mark.parametrize("recipe,operation,arguments", INSERT_CASES)
def test_missing_insert_id_is_not_committed(recipe, operation, arguments):
    module = load_recipe(recipe)
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.lastrowid = None

    with pytest.raises(RuntimeError, match="auto-increment ID"):
        getattr(module, operation)(conn, *arguments)

    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    cursor.close.assert_called_once()


def test_delete_session_removes_children_before_session():
    module = load_recipe("01_agent_state.py")
    conn = MagicMock()
    cursor = conn.cursor.return_value

    module.delete_session(conn, "cookbook-agent-state-demo")

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert [sql.split()[2] for sql in statements] == [
        "cookbook_agent_tool_calls",
        "cookbook_agent_messages",
        "cookbook_agent_sessions",
    ]
    assert all(
        call.args[1] == ["cookbook-agent-state-demo"] for call in cursor.execute.call_args_list
    )
    conn.commit.assert_called_once()
    cursor.close.assert_called_once()


@pytest.mark.parametrize(
    "recipe,session_key",
    [
        ("01_agent_state.py", "cookbook-agent-state-demo"),
        ("04_agent_loop.py", "cookbook-agent-loop-demo"),
    ],
)
def test_recipe_deletes_previous_demo_session_before_creating(recipe, session_key, monkeypatch):
    module = load_recipe(recipe)
    state = module._agent_state if recipe == "04_agent_loop.py" else module
    events = []
    monkeypatch.setattr(module.pycubrid, "connect", lambda **kwargs: MagicMock())
    monkeypatch.setattr(state, "setup_schema", lambda conn: None)
    monkeypatch.setattr(state, "delete_session", lambda conn, key: events.append(("delete", key)))

    def create_session(conn, key, **kwargs):
        events.append(("create", key))
        raise RuntimeError("stop after create")

    monkeypatch.setattr(state, "create_session", create_session)

    with pytest.raises(RuntimeError, match="stop after create"):
        module.main()

    assert events == [("delete", session_key), ("create", session_key)]


@pytest.mark.parametrize("recipe", ["01_agent_state.py", "03_rag_metadata.py", "04_agent_loop.py"])
def test_recipe_closes_connection_on_setup_error(recipe, monkeypatch):
    module = load_recipe(recipe)
    conn = MagicMock()
    monkeypatch.setattr(module.pycubrid, "connect", lambda **kwargs: conn)
    setup_owner = module._agent_state if recipe == "04_agent_loop.py" else module
    setup_name = "setup" if recipe == "03_rag_metadata.py" else "setup_schema"
    monkeypatch.setattr(
        setup_owner, setup_name, MagicMock(side_effect=RuntimeError("setup failed"))
    )

    with pytest.raises(RuntimeError, match="setup failed"):
        module.main()

    conn.close.assert_called_once()


def test_chatbot_disposes_engine_on_setup_error(monkeypatch):
    module = load_recipe("05_chatbot_backend.py", monkeypatch)
    engine = MagicMock()
    monkeypatch.setattr(module.sa, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        module.Base.metadata, "create_all", MagicMock(side_effect=RuntimeError("setup failed"))
    )

    with pytest.raises(RuntimeError, match="setup failed"):
        module.main()

    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    "response",
    ["", '{"id": 1, "error": {"message": "failed"}}', '{"id": 2, "result": {}}', '{"id": 1}'],
)
def test_mcp_protocol_errors_fail(response, monkeypatch):
    module = load_recipe("02_mcp_toolchain.py")
    selector = MagicMock()
    monkeypatch.setattr(module.selectors, "DefaultSelector", lambda: selector)
    proc = MagicMock(stdin=io.StringIO(), stdout=io.StringIO(response))

    with pytest.raises(RuntimeError):
        module.send_mcp_request(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})


def test_mcp_tool_error_cannot_report_success(monkeypatch):
    module = load_recipe("02_mcp_toolchain.py")
    proc = MagicMock()
    monkeypatch.setattr(module, "start_mcp_server", lambda: proc)
    replies = iter(
        [
            {"result": {"serverInfo": {"name": "cubrid-mcp-server"}}},
            {"result": {"tools": [{"name": "all_table_names"}, {"name": "execute_query"}]}},
            {"result": {"isError": True, "content": [{"text": "Database unavailable"}]}},
        ]
    )
    monkeypatch.setattr(module, "send_mcp_request", lambda *args: next(replies))

    with pytest.raises(RuntimeError, match="table query failed"):
        module.main()

    proc.terminate.assert_called_once()
    proc.wait.assert_called_once_with(timeout=5)


def test_live_fixture_decodes_credentials_and_restores_environment(monkeypatch):
    module = load_live_suite()
    monkeypatch.setattr(
        module, "CUBRID_TEST_URL", "cubrid://user%40name:p%3Ass@db.example:33007/testdb"
    )
    connect = MagicMock()
    monkeypatch.setattr(module.pycubrid, "connect", connect)
    monkeypatch.setenv("CUBRID_HOST", "original-host")
    monkeypatch.setenv("DATABASE_URL", "original-url")

    with pytest.MonkeyPatch.context() as scoped:
        fixture = module.setup_database_url.__wrapped__(scoped, RECIPE_ROOT / "01_agent_state.py")
        next(fixture)
        assert os.environ["CUBRID_USER"] == "user@name"
        assert os.environ["CUBRID_PASSWORD"] == "p:ss"
        assert os.environ["DATABASE_URL"].startswith("cubrid+pycubrid://")
        fixture.close()

    assert os.environ["CUBRID_HOST"] == "original-host"
    assert os.environ["DATABASE_URL"] == "original-url"
    assert connect.call_count == 2  # before and after the recipe
    assert connect.call_args.kwargs["user"] == "user@name"
    assert connect.call_args.kwargs["password"] == "p:ss"
    assert connect.call_args.kwargs["connect_timeout"] == 10
    assert connect.call_args.kwargs["read_timeout"] == 15


def test_live_timeout_terminates_owned_process_group(monkeypatch):
    module = load_live_suite()
    process = MagicMock(pid=12345)
    process.communicate.side_effect = [subprocess.TimeoutExpired("recipe", 60), ("out", "err")]
    popen = MagicMock()
    popen.return_value.__enter__.return_value = process
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    kill_group = MagicMock()
    monkeypatch.setattr(module.os, "killpg", kill_group)

    with pytest.raises(pytest.fail.Exception, match="exceeded 60 seconds"):
        module.test_ai_agent_recipes_runs_without_errors(RECIPE_ROOT / "02_mcp_toolchain.py")

    kill_group.assert_called_once_with(12345, signal.SIGKILL)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert process.communicate.call_count == 2


STATE_RECIPES = [
    "01_agent_state.py",
    "03_rag_metadata.py",
    "04_agent_loop.py",
    "05_chatbot_backend.py",
]
# One intentionally wrong expectation per recipe: (state key, wrong value).
WRONG_EXPECTATIONS = {
    "01_agent_state.py": ("tags", ["demo"]),
    "03_rag_metadata.py": ("latest_retrieval", None),
    "04_agent_loop.py": ("products", []),
    "05_chatbot_backend.py": ("conversations", [("CUBRID + AI Demo", "closed")]),
}


@pytest.mark.parametrize("recipe", STATE_RECIPES)
def test_live_state_assertion_rejects_a_wrong_expectation(recipe):
    module = load_live_suite()
    expected = module.expected_state(recipe)
    module.assert_state(dict(expected), expected, recipe)

    key, wrong = WRONG_EXPECTATIONS[recipe]
    with pytest.raises(AssertionError, match=f"{key}: expected"):
        module.assert_state(expected, {**expected, key: wrong}, recipe)
    with pytest.raises(AssertionError, match="unexpected_key"):
        module.assert_state({**expected, "unexpected_key": 1}, expected, recipe)


def test_live_rag_expectation_counts_one_log_row_per_run():
    module = load_live_suite()
    first = module.expected_state("03_rag_metadata.py")
    second = module.expected_state("03_rag_metadata.py", runs=2)
    assert first["table_rows"]["cookbook_rag_retrieval_log"] == 1
    assert second["table_rows"]["cookbook_rag_retrieval_log"] == 2
    with pytest.raises(AssertionError, match="table_rows"):
        module.assert_state(first, second, "03_rag_metadata.py")


def test_live_agent_loop_masks_only_the_database_dependent_table_list():
    module = load_live_suite()
    assert module.mask_tables("Based on the data: Found 7 tables: a, b") == (
        "Based on the data: Found <n> tables: <names>"
    )
    assert module.mask_tables("Connection OK") == "Connection OK"


def run_live_suite(extra_env):
    """Run the live module in a child pytest with a controlled spec-gate environment."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CUBRID_TEST_URL", "CUBRID_SPEC_GATE"}
    }
    env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_ai_agent.py",
            "-x",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=RECIPE_ROOT.parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_live_suite_skips_without_url_outside_the_spec_gate():
    result = run_live_suite({})
    assert result.returncode == 0, result.stdout + result.stderr
    assert " skipped" in result.stdout and "passed" not in result.stdout


def test_spec_gate_fails_closed_without_url():
    result = run_live_suite({"CUBRID_SPEC_GATE": "1"})
    assert result.returncode != 0, result.stdout
    assert "CUBRID_SPEC_GATE=1 requires CUBRID_TEST_URL" in result.stdout
    assert "skipped" not in result.stdout


def test_spec_gate_fails_closed_on_unreachable_database():
    # Port 1 on the loopback interface refuses connections immediately.
    result = run_live_suite(
        {"CUBRID_SPEC_GATE": "1", "CUBRID_TEST_URL": "cubrid+pycubrid://dba@127.0.0.1:1/testdb"}
    )
    assert result.returncode != 0, result.stdout
    assert "OperationalError" in result.stdout
    assert "passed" not in result.stdout and "skipped" not in result.stdout
