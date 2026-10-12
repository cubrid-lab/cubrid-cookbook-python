# Quick Start

The site version of [`GETTING_STARTED.md`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/GETTING_STARTED.md) — the repository file remains the source of truth.

## 0. Start CUBRID (all paths)

```bash
docker compose up -d        # CUBRID 11.2 on localhost:33000, database testdb
```

Readiness takes up to a minute on first start:

```bash
docker exec cubrid-cookbook bash -lc "csql -u dba testdb -c 'SELECT 1;'"
```

## 1. Five-minute first query (pycubrid)

```bash
pip install pycubrid
python fundamentals/pycubrid/01_connect.py
```

The expected output is checked by CI on CUBRID 11.2 and 11.4 — compare against [`fundamentals/pycubrid/expected/01_connect.expected`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/pycubrid/expected/01_connect.expected). From here, `fundamentals/` walks through CRUD, transactions, parameterized queries, collections, LOBs, and window functions.

## 2. ORM and application templates (sqlalchemy-cubrid)

```bash
pip install 'sqlalchemy-cubrid[pycubrid]'   # pulls SQLAlchemy 2.x and pycubrid
python fundamentals/sqlalchemy/01_connect_and_session.py
```

Production-shaped starters live in `templates/` — a FastAPI service, Flask app, Django app, Streamlit dashboard, Celery async worker, a pandas batch ETL, and AI-agent examples (`templates/ai-agent`: agent state, MCP tool chain, RAG metadata). The dashboard is a one-command demo:

```bash
cd templates/dashboard
docker compose up -d           # CUBRID 11.4 + Streamlit at http://localhost:8501
```

## 3. Natural language over the database (cubrid-mcp-server)

```bash
uvx cubrid-mcp-server          # stdio MCP server; requires CUBRID_* env vars
```

Claude Desktop / Claude Code / Cursor config blocks are in the [cubrid-mcp-server README](https://github.com/cubrid-lab/cubrid-mcp-server#mcp-client-integration). Once connected, ask:

1. "What tables are in this database?" → `all_table_names`
2. "Show the structure of `cookbook_sales`" → `describe_table`
3. "Top 5 products by revenue" → `execute_query` (read-only)
4. "Drop the orders table" → **rejected** by the read-only whitelist (this refusal is the feature)

## Recorded walkthroughs

Screen recordings of the examples running against CUBRID. Every command and
every line of output in them is real; the waits for the CUBRID health check and
the dashboard's first `pip install` are cut. How they were made, with versions
and hashes: [`demos/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/demos).

### Streamlit dashboard: one command

`docker compose up -d` in `templates/dashboard`, then the table viewer at
http://localhost:8501 (CUBRID 11.4).

<video controls preload="metadata" playsinline width="100%">
  <source src="../assets/videos/dashboard.mp4" type="video/mp4">
  Your browser cannot play this video. Use the download link below.
</video>

[Download the dashboard walkthrough](assets/videos/dashboard.mp4).

### AI agent state management

`templates/ai-agent/01_agent_state.py` stores a session, its messages and a tool
call in CUBRID; `04_agent_loop.py` runs a query, think, act, observe loop and
persists every turn. The planner is a heuristic, not an LLM.

<video controls preload="metadata" playsinline width="100%">
  <source src="../assets/videos/agent-state.mp4" type="video/mp4">
  Your browser cannot play this video. Use the download link below.
</video>

[Download the agent state walkthrough](assets/videos/agent-state.mp4).

### MCP tool chain

`templates/ai-agent/02_mcp_toolchain.py` starts `cubrid-mcp-server` over stdio,
lists its tools, calls them and shows the read-only whitelist rejecting a
`DROP TABLE`. No LLM client or API key is involved.

<video controls preload="metadata" playsinline width="100%">
  <source src="../assets/videos/mcp-toolchain.mp4" type="video/mp4">
  Your browser cannot play this video. Use the download link below.
</video>

[Download the MCP tool chain walkthrough](assets/videos/mcp-toolchain.mp4).

## Verify a full checkout

Use a Python 3.11+ virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 or later
make up                       # start CUBRID and wait until it is ready
make deps                     # drivers, pytest and every golden-backed example's requirements
make verify                   # runs every golden-backed example against your local CUBRID
```

`make deps` installs everything in one pip call and honours `PIP_CONSTRAINT`. `make verify` stops early with "run `make deps` first" when an example requirement is missing, limits each script to `VERIFY_TIMEOUT` seconds (default 60), and reports each result as pass, mismatch, exec error, timeout, normalizer/read error or skip.
