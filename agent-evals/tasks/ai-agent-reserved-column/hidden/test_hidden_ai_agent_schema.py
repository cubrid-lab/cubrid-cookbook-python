"""Evaluator-owned checks for the ai-agent-reserved-column task.

They read the recipes' DDL and the SQL the message helpers send through a fake
connection; no database is needed. This is offline evidence only: it does not
show that a live CUBRID accepts the schema. Copied into the candidate's worktree
only by ``scripts/agent_eval.py run``.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ("01_agent_state.py", "03_rag_metadata.py")
# CUBRID reserved words a recipe column is likely to hit (see pitfalls/reserved-words).
RESERVED = {"role", "value", "count", "data", "user", "date", "time", "order", "group", "level"}
CREATE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)", re.S | re.I)
CONSTRAINT = {"primary", "foreign", "unique", "constraint", "key", "index", "check"}
# The tables each recipe's helpers need, with the columns that keep their names
# (the renamed message-role column may take any non-reserved name).
REQUIRED = {
    "01_agent_state.py": {
        "agent_sessions": {"id", "session_key", "agent_name", "status", "tags", "created_at"},
        "agent_messages": {"id", "session_id", "content", "metadata", "created_at"},
        "agent_tool_calls": {"id", "session_id", "tool_name", "arguments", "result", "status"},
    },
    "03_rag_metadata.py": {
        "rag_documents": {"id", "title", "source", "content", "metadata", "tags", "chunk_count"},
        "rag_chunks": {"id", "document_id", "chunk_index", "content"},
        "rag_retrieval_log": {"id", "query_text", "llm_response"},
    },
}


def _module(name):
    spec = importlib.util.spec_from_file_location(name[:-3], ROOT / "templates" / "ai-agent" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables(module):
    tables = {}
    for ddl in module.DDL:
        match = CREATE.search(ddl)
        if not match:
            continue
        columns, depth, part = {}, 0, ""
        for char in match.group(2) + ",":
            depth += {"(": 1, ")": -1}.get(char, 0)
            if char == "," and depth == 0:
                words = part.split()
                if words and words[0].lower() not in CONSTRAINT:
                    columns[words[0].strip('"[]`').lower()] = words[1].upper()
                part = ""
            else:
                part += char
        tables[match.group(1).lower()] = columns
    return tables


@pytest.mark.parametrize("recipe", RECIPES)
def test_columns_avoid_reserved_words_and_text(recipe):
    tables = _tables(_module(recipe))
    for table, needed in REQUIRED[recipe].items():
        assert table in tables, f"{recipe} no longer creates {table}"
        assert needed <= set(tables[table]), (table, sorted(needed - set(tables[table])))
    for table, columns in tables.items():
        assert not RESERVED & set(columns), (table, sorted(RESERVED & set(columns)))
        assert "TEXT" not in columns.values(), (table, columns)


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append(sql)

    def fetchall(self):
        return []

    def __iter__(self):
        return iter([])

    def fetchone(self):
        return None

    def close(self):
        pass


class _Connection:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def get_last_insert_id(self):
        return 1


def test_message_helpers_use_the_declared_columns():
    module = _module("01_agent_state.py")
    declared = set(_tables(module)["agent_messages"])
    conn = _Connection()
    module.add_message(conn, 1, "user", "hello")
    module.get_conversation(conn, 1)
    used = set()
    for sql in conn.log:
        insert = re.search(r"INSERT\s+INTO\s+agent_messages\s*\(([^)]*)\)", sql, re.I)
        select = re.search(r"SELECT\s+(.*?)\s+FROM\s+agent_messages", sql, re.I | re.S)
        for match in (insert, select):
            if match:
                used |= {c.strip().strip('"[]`').lower() for c in match.group(1).split(",")}
    assert used and used <= declared, sorted(used - declared)


def test_every_agent_messages_query_names_declared_columns():
    """All SQL text in the recipe, ``main()`` included: column lists and predicates."""
    path = ROOT / "templates" / "ai-agent" / "01_agent_state.py"
    declared = set(_tables(_module("01_agent_state.py"))["agent_messages"])
    texts = [
        node.value
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    used = set()
    for sql in texts:
        if "agent_messages" not in sql or re.search(r"CREATE\s+TABLE", sql, re.I):
            continue
        for pattern in (
            r"INSERT\s+INTO\s+agent_messages\s*\(([^)]*)\)",
            r"SELECT\s+(.*?)\s+FROM\s+agent_messages",
        ):
            for match in re.finditer(pattern, sql, re.I | re.S):
                used |= {c.strip().strip('"[]`').lower() for c in match.group(1).split(",")}
        where = re.search(r"\bWHERE\b(.*)", sql, re.I | re.S)
        if where:
            used |= {
                m.group(1).lower()
                for m in re.finditer(
                    r"\b(\w+)\s*(?:=|<>|!=|<=|>=|<|>|\bLIKE\b|\bIN\b)", where.group(1), re.I
                )
            }
    used.discard("")
    assert used and used <= declared, sorted(used - declared)
