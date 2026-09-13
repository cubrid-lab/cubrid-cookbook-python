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
