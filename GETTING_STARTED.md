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

### A lab created before the October 2026 lab fix

`docker-compose.yml` now keeps the database in named volumes and gives the
container a fixed host name (#385). A lab started from the earlier file breaks
the first time the new file recreates its container: CUBRID records the old
container's host name, so the database fails to open (`-353 Failed to connect
to database server`). Your data is still there. Recover it as follows, from the
repository folder. **Do not run `docker compose down -v`, which deletes the
data**; if the lab holds anything you need, copy it out first.

If you started the lab without `CUBRID_VERSION` (CUBRID 11.2, the default),
point the database at the new host name and restart:

```bash
docker compose up -d
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-cookbook/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
python3 scripts/wait_for_cubrid.py
```

If you started it with `CUBRID_VERSION=11.4`, its database sits in a volume
without a name. Before you update the repository, note that volume and stop
the lab:

```bash
OLD=$(docker inspect cubrid-cookbook --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

Then update the repository (`git pull`), copy the database into the new named
volume, fix its host name and start the lab:

```bash
CUBRID_VERSION=11.4 docker compose create
NEW=$(docker inspect cubrid-cookbook --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-cookbook/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
CUBRID_VERSION=11.4 docker compose up -d
python3 scripts/wait_for_cubrid.py
```

When your data is back, `docker volume rm "$OLD"` removes the old copy.

## 1. Five-minute first query (pycubrid)

```bash
pip install pycubrid
python fundamentals/pycubrid/01_connect.py
```

The expected output is checked by CI on CUBRID 11.2 and 11.4 — compare against `fundamentals/pycubrid/expected/01_connect.expected`. From here, `fundamentals/` walks through CRUD, transactions, parameterized queries, collections, LOBs, and window functions — every directory with an `expected/` folder is verified by `make verify`.

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

## Verify a full checkout

Use a Python 3.11+ virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 or later
make up                       # start CUBRID and wait until it is ready
make deps                     # drivers, pytest and every golden-backed example's requirements
make verify                   # runs every golden-backed example against your local CUBRID
```

`make deps` installs everything in one pip call and honours `PIP_CONSTRAINT`. `make verify` stops early with "run `make deps` first" when an example requirement is missing, limits each script to `VERIFY_TIMEOUT` seconds (default 60), and reports each result as pass, mismatch, exec error, timeout, normalizer/read error or skip.

## Where to go next

| Goal | Start at |
|---|---|
| Copy-and-customize starters | `templates/` |
| JDBC-to-Python migration | `migration/java-to-python/` |
| Performance patterns | `performance/` |
| Known CUBRID quirks | `pitfalls/`, `KNOWN_ISSUES.md` |
| Supported versions | `SUPPORT_MATRIX.md` |
