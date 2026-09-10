# Getting Started

Three paths, from a 5-minute first query to a natural-language MCP session. Everything installs from PyPI — no git checkouts, no C compiler.

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

The expected output is checked by CI on CUBRID 11.2 and 11.4 — compare against `fundamentals/pycubrid/expected/01_connect.expected`. From here, `fundamentals/` walks through CRUD, transactions, parameterized queries, collections, LOBs, and window functions — every directory with an `expected/` folder is verified by `make verify`.

## 2. ORM and application templates (sqlalchemy-cubrid)

```bash
pip install sqlalchemy-cubrid   # pulls SQLAlchemy 2.x
python fundamentals/sqlalchemy/01_engine_and_connection.py
```

Production-shaped starters live in `templates/` — a FastAPI service, Flask app, Django app, Streamlit dashboard, Celery async worker, and a pandas batch ETL. The dashboard is a one-command demo:

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

## Verify a full checkout

```bash
pip install pycubrid sqlalchemy sqlalchemy-cubrid
make verify                   # runs every golden-backed example against your local CUBRID
```

## Where to go next

| Goal | Start at |
|---|---|
| Copy-and-customize starters | `templates/` |
| JDBC-to-Python migration | `migration/java-to-python/` |
| Performance patterns | `performance/` |
| Known CUBRID quirks | `pitfalls/`, `KNOWN_ISSUES.md` |
| Supported versions | `SUPPORT_MATRIX.md` |
