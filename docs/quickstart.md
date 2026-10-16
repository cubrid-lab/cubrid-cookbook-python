# Quick Start

This page used to repeat [Getting Started](getting-started.md). Its sections now
point to the one place that keeps each step, and it keeps the recorded
walkthroughs.

- **New to CUBRID?** Start with the beginner tutorial,
  [your first CUBRID database from Python](first-cubrid.md): five short lessons
  from a local practice database to a first query, `commit`, `rollback` and a safe
  clean-up.
- **Already know which path you want?** Use [Getting Started](getting-started.md).

## 0. Start CUBRID (all paths)

Starting the lab and waiting until it is ready: lesson 1 of the tutorial,
[Prepare the lab](first-cubrid.md#2-prepare-the-lab), or
[Getting Started](getting-started.md#0-start-cubrid-all-paths).

## 1. Five-minute first query (pycubrid)

See [Getting Started](getting-started.md#1-five-minute-first-query-pycubrid). A
guided version is [Lesson 2: Run your first query](first-cubrid-first-query.md).

## 2. ORM and application templates (sqlalchemy-cubrid)

See [Getting Started](getting-started.md#2-orm-and-application-templates-sqlalchemy-cubrid)
and the [SQLAlchemy quickstart](quickstart-sqlalchemy.md).

## 3. Natural language over the database (cubrid-mcp-server)

See [Getting Started](getting-started.md#3-natural-language-over-the-database-cubrid-mcp-server).

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

See [Getting Started](getting-started.md#verify-a-full-checkout).
