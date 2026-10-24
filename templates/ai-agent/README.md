# AI Agent Template

Production-shaped template that uses CUBRID as the state store for AI
agents, combined with the CUBRID MCP server to build the full
**natural language → safe query → response** pipeline.

## Examples

| File | Topic | Techniques |
|------|-------|------------|
| `01_agent_state.py` | Store agent sessions, messages, and tool calls in CUBRID | pycubrid, JSON columns, SET |
| `02_mcp_toolchain.py` | Invoke the MCP server programmatically (no Claude required) | cubrid-mcp-server, subprocess |
| `03_rag_metadata.py` | RAG document store — full text, metadata, chunk tracking | pycubrid, JSON, SET, SEQUENCE |
| `04_agent_loop.py` | Query → think → act → observe agent cycle (direct pycubrid execution; no MCP server) | pycubrid, agent state |
| `05_chatbot_backend.py` | Chatbot backend — conversation history and user preferences | SQLAlchemy ORM, JSON columns |

## Quick Start

```bash
# 1. Start CUBRID (root docker-compose.yml)
cd ../../           # cookbook root
docker compose up -d

# 2. Install dependencies
cd templates/ai-agent
pip install -r requirements.txt

# 3. Run the examples
python 01_agent_state.py       # agent state management
python 02_mcp_toolchain.py     # MCP tool chain
python 03_rag_metadata.py      # RAG metadata
python 04_agent_loop.py        # agent loop
python 05_chatbot_backend.py   # chatbot backend
```

Recipes 01–04 read `CUBRID_HOST`, `CUBRID_PORT`, `CUBRID_DATABASE`,
`CUBRID_USER`, and `CUBRID_PASSWORD` (defaults: localhost, 33000, testdb, dba,
empty password). Recipe 05 reads `DATABASE_URL`, defaulting to
`cubrid+pycubrid://dba@localhost:33000/testdb`.

The examples use fixed, recipe-owned demonstration data: the session keys
`cookbook-agent-state-demo` and `cookbook-agent-loop-demo`, the username
`cookbook_demo_alice`, and three sample documents whose metadata carries
`"recipe": "cookbook-ai-agent-rag-demo"`. Each run first deletes only its own
previous copy of that data, so every recipe can be run again on the same
database; other rows, including ones with the same source URL, are left alone,
and `cookbook_rag_retrieval_log` keeps accumulating.
Recipe 04 creates and seeds `cookbook_agent_products` so its product query
does not depend on another example. Database connections and the ORM engine
are closed even if a demonstration raises.

With released pycubrid 1.7.x, INSERT IDs must be read from `cursor.lastrowid`
before commit. Collection members are bound inside `{?, ...}` expressions;
`TABLE(collection)` reads SET and SEQUENCE elements as ordinary scalar rows.
This template keeps the `pycubrid>=1.7` floor and the default connection, which returns
collection columns as raw bytes. `decode_collections=True` and typed
`Set`/`Multiset`/`Sequence` binding (pycubrid 1.9+) are shown in the
[collection recipe](../../fundamentals/sqlalchemy/07_collection_types.py). The MCP demo completes the initialization handshake,
requires successful read responses, and verifies that writes are rejected in
read-only mode; connection or protocol errors fail instead of printing success.

## Tests

Run these commands from the repository root:

```bash
pip install -r templates/ai-agent/requirements.txt pytest
python -m pytest templates/ai-agent/tests/test_offline.py -q
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" \
  python -m pytest templates/ai-agent/tests/test_live.py -v
```

The live suite requires a dedicated test database: before and after each
script it drops only that script's `agent_*`, `rag_*`, or `chat_*` tables
(foreign-key children first), plus `cookbook_agent_products` for recipe 04; the
MCP case (02) drops the agent-state tables it uses as its read-only target.
It restores environment variables and always uses the pycubrid SQLAlchemy
backend, even if the supplied URL uses the legacy `cubrid://` scheme.

After each run a separate connection reads back what the script persisted and
compares it with explicit expectations in `templates/ai-agent/tests/test_live.py`, ignoring
auto-increment IDs and timestamps and resolving foreign keys through joins:

- **01** — the `cookbook-agent-state-demo` session, its tags, its three messages
  (with the assistant's JSON metadata) and its tool call, and the table row counts.
- **02** — an in-process MCP session checks the `initialize`
  handshake, that `tools/list` exposes the tools in `scripts/mcp_smoke.py`, that
  `all_table_names` returns the same owner-qualified list of user tables as `db_class` (structured
  result) and that `SELECT COUNT(*)` works; the rejected `DROP TABLE` leaves the
  target table and its sentinel row in place, checked without the MCP server.
- **03** — each sample document's source, metadata, tags and chunk count, each
  chunk's token count and `embedding_ref`, and the latest retrieval-log row
  (query, retrieved document, response, scores).
- **04** — the agent-loop session's nine messages and three tool calls in order,
  the product rows, and the row counts; the database-dependent table list and
  timings are masked.
- **05** — the demo user's preferences, its conversation and the four messages
  with turn numbers and token counts.

A second live case runs each script twice without resetting its tables, so a
rerun on the same database is covered too; between the runs it inserts a
reader's look-alike row (session key `demo-001`, username `alice`, a document
with a sample source URL) and checks that the rerun keeps it. The second run
must leave the same state as the first, with new root-row IDs (the old
fixed-key rows were deleted, not reused); the retrieval log of recipe 03 is
append-only and gains one row per run.
Without `CUBRID_TEST_URL`, the eleven live cases skip; offline tests still run.
Each script runs in its own process with a 60-second limit; cleanup connections
have a 10-second connect timeout and a 15-second read timeout. CI runs the
live suite through the same commands, twice on the same dedicated database to
catch stale demonstration keys after teardown: the smoke-test matrix runs the
full `make verify` and then `make verify-ai-agent` on both CUBRID 11.2 and 11.4
for every `main` push, the nightly schedule and release verification, and the
CUBRID 11.4 pull-request smoke lane runs `make verify-ai-agent` twice when a pull
request touches this template or its tests. Both runs keep their evidence
(`.live-evidence/ai-agent-run-1/` and `-run-2/` in the `live-evidence-*` workflow
artifact; not for a release workflow call).

`make verify-ai-agent` (also part of the full `make verify`) runs the live suite
fail-closed (`CUBRID_LIVE_GATE=1`): a missing `CUBRID_TEST_URL`, an unreachable
database, a database that already holds `cookbook_*` tables, a table left behind or
any skipped case fails, and the JUnit report and a summary are written to
`.live-evidence/ai-agent/`. Point it at a dedicated, empty database, not the
`make up` database the golden examples use; `make test` runs the offline suite:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33005/testdb" make verify-ai-agent
```

## Architecture

```
User Query
    ↓
┌──────────────────────────────────────────┐
│  AI Agent (Python)                       │
│  ┌───────────┐  ┌────────────┐           │
│  │ Think     │→ │ Act        │           │
│  │ (LLM)     │  │ (tools)    │           │
│  └───────────┘  └────────────┘           │
│       ↓               ↓                  │
│  ┌───────────┐  ┌────────────┐           │
│  │ Observe   │→ │ Respond    │           │
│  └───────────┘  └────────────┘           │
│       ↓               ↓                  │
│  ┌────────────────────────────────────┐  │
│  │ CUBRID (state store)               │  │
│  │ · cookbook_agent_sessions          │  │
│  │ · cookbook_agent_messages (JSON)   │  │
│  │ · cookbook_agent_tool_calls (JSON) │  │
│  │ · cookbook_rag_documents (SET)     │  │
│  │ · cookbook_rag_chunks              │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

The `02_mcp_toolchain.py` example invokes the CUBRID MCP server and its
read-only whitelist. The `04_agent_loop.py` example uses the same tool names
for planning but executes them directly through pycubrid; it does not provide
MCP server or whitelist enforcement.

> **Warning:** `execute_query` in `04_agent_loop.py` runs whatever SQL it is
> given, and recipes 01–04 connect as `dba` by default. Once a real LLM writes
> that SQL (see [Connecting a Real LLM](#connecting-a-real-llm)), it can modify
> or drop data. Before connecting one, route the tool calls through
> `cubrid-mcp-server` in read-only mode as `02_mcp_toolchain.py` does, or
> validate the statement as a read-only query yourself, and connect as a
> least-privilege user.

## Why CUBRID for AI Agents

| Feature | Benefit |
|---------|---------|
| **JSON columns** | Store and query LLM responses and tool outputs in structured form |
| **SET / SEQUENCE** | Collection types for document tagging, conversation ordering, search logs |
| **MCP read-only whitelist** | Constrain agent queries safely to SELECT-only access |
| **Opt-in write mode** | Allow a single atomic DML statement when explicitly enabled |
| **Transactions** | Consistent agent state transitions |

## Connecting a Real LLM

The template ships a `simulate_llm_response()` placeholder — replace it
with a real API call:

```python
# OpenAI
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4", messages=[{"role": "user", "content": user_message}]
)

# Anthropic Claude
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514", messages=[{"role": "user", "content": user_message}]
)
```

Alternatively, connect `cubrid-mcp-server` to Claude Desktop and query
CUBRID directly in natural language — see [GETTING_STARTED.md](../../GETTING_STARTED.md).
