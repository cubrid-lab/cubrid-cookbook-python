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
| `04_agent_loop.py` | Query → think → act → observe agent cycle | pycubrid, agent state |
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

The examples retain their demonstration data, including fixed session keys
and the `alice` username. Use a fresh database for a first manual run.
Recipe 04 creates and seeds `cookbook_agent_products` so its product query
does not depend on another example. Database connections and the ORM engine
are closed even if a demonstration raises.

With released pycubrid 1.7.x, INSERT IDs must be read from `cursor.lastrowid`
before commit. Collection members are bound inside `{?, ...}` expressions;
`TABLE(collection)` reads SET and SEQUENCE elements as ordinary scalar rows.
See the [collection recipe](../../fundamentals/sqlalchemy/07_collection_types.py)
for the driver limitations. The MCP demo completes the initialization handshake,
requires successful read responses, and verifies that writes are rejected in
read-only mode; connection or protocol errors fail instead of printing success.

## Tests

Run these commands from the repository root:

```bash
pip install -r templates/ai-agent/requirements.txt pytest
python -m pytest tests/test_ai_agent_offline.py -q
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" \
  python -m pytest tests/test_ai_agent.py -v
```

The live suite requires a dedicated test database: before and after each
script it drops only that script's `agent_*`, `rag_*`, or `chat_*` tables
(foreign-key children first), plus `cookbook_agent_products` for recipe 04.
It restores environment variables and always uses the pycubrid SQLAlchemy
backend, even if the supplied URL uses the legacy `cubrid://` scheme.
Without `CUBRID_TEST_URL`, the five live cases skip; offline tests still run.
Each script runs in its own process with a 60-second limit; cleanup connections
have a 10-second connect timeout and a 15-second read timeout. The smoke-test
matrix runs the suite twice on both CUBRID 11.2 and 11.4 for every `main` push,
the nightly schedule and release verification, and the CUBRID 11.4 pull-request
smoke lane runs it twice when a pull request touches this template or golden
examples, to catch stale demonstration keys after teardown.

## Architecture

```
User Query
    ↓
┌─────────────────────────────────┐
│  AI Agent (Python)              │
│  ┌───────────┐  ┌────────────┐ │
│  │ Think     │→ │ Act (MCP)  │ │
│  │ (LLM)     │  │ (read-only)│ │
│  └───────────┘  └────────────┘ │
│       ↓               ↓        │
│  ┌───────────┐  ┌────────────┐ │
│  │ Observe   │→ │ Respond    │ │
│  └───────────┘  └────────────┘ │
│       ↓               ↓        │
│  ┌──────────────────────────┐  │
│  │ CUBRID (state store)     │  │
│  │ · agent_sessions         │  │
│  │ · agent_messages (JSON)  │  │
│  │ · agent_tool_calls (JSON)│  │
│  │ · rag_documents (SET)    │  │
│  │ · rag_chunks             │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
```

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
