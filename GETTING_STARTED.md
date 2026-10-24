# Getting Started

Three paths, from a 5-minute first query to a natural-language MCP session. Everything installs from PyPI — no git checkouts, no C compiler.

New to CUBRID? Start with the beginner tutorial, [your first CUBRID database from Python](quickstart/first-cubrid/README.md): it explains the lab and the connection settings and goes one step at a time. This page is for choosing a path, verifying a full checkout and recovering an older lab.

## 0. Start CUBRID (all paths)

```bash
make docker-up              # CUBRID 11.2 on 127.0.0.1:33000, database testdb; waits until it answers
```

`make docker-up` runs `docker compose up -d` for the root `docker-compose.yml`
service `cubrid` and then waits (up to 120 seconds) until `testdb` answers a
query inside the container. Without `make`, run `docker compose up -d` and check
readiness yourself; it takes up to a minute on first start:

```bash
docker compose exec cubrid csql -u dba testdb -c 'SELECT 1'
```

The Docker lifecycle has three commands:

| Command | What it does | Database data |
|---|---|---|
| `make docker-up` | starts the lab (`CUBRID_VERSION=11.4` selects another image) | kept from the last run |
| `make docker-down` | stops and removes the container and network | **kept** in the named volumes |
| `make docker-clean` | removes the container, network and volumes | **deleted** |

`make up` and `make down` are aliases of `make docker-up` and `make docker-down`.
The broker listens on `127.0.0.1` only. `CUBRID_TEST_PORT=<port>` publishes it on
another host port, for example for a second lab under its own
`COMPOSE_PROJECT_NAME`, but the examples and `make verify` expect the lab on `33000`.

### A lab created before the October 2026 lab changes

`docker-compose.yml` keeps the database in named volumes and registers it for
the host `localhost` (`CUBRID_DB_HOST`), so any new container opens it
(#385, #436). A lab started from an earlier file breaks the first time the new file
recreates its container: CUBRID recorded the old container's host name
(`cubrid-cookbook` or a random container ID), so the database fails to open
(`-353 Failed to connect to database server`). Your data is still there. Recover
it as follows, from the repository folder. **Do not run `make docker-clean` or
`docker compose down -v`, which delete the data**; if the lab holds anything you
need, copy it out first.

If its database is already in the named volumes (any CUBRID 11.2 lab, or an 11.4
lab started after #385), point the database at `localhost` and restart. Add
`CUBRID_VERSION=11.4` to the first command for an 11.4 lab:

```bash
docker compose up -d
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
python3 scripts/wait_for_cubrid.py
```

If you started an 11.4 lab with `CUBRID_VERSION=11.4` before #385, its database
sits in a volume without a name. Before you update the repository, note that
volume and stop the lab:

```bash
OLD=$(docker inspect "$(docker compose ps -aq cubrid)" --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

Then update the repository (`git pull`), copy the database into the new named
volume, fix its host name and start the lab:

```bash
CUBRID_VERSION=11.4 docker compose create
NEW=$(docker inspect "$(docker compose ps -aq cubrid)" --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
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
make deps                     # drivers, pytest and every example's requirements
make test                     # 1. unit and mocked tests: no database, no Docker
make docker-up                # start CUBRID and wait until it is ready
make verify                   # 2. full live verification (needs two more databases, see below)
```

The standard sequence is `make test`, then `make verify`. `make deps` installs everything in one pip call and honours `PIP_CONSTRAINT`. `make test` writes its results to `test-results/test/` (`summary.json` and one JUnit file per suite).

`make verify` is the full live verification: every golden plus the FastAPI quickstart, Flask/FastAPI, Django/Celery, Streamlit, AI agent/MCP/RAG, migration and performance suites. Besides the `make docker-up` database it needs two dedicated, empty CUBRID databases in `CUBRID_TEST_URL` and `CUBRID_DASHBOARD_TEST_URL`, fails if anything is unreachable, skipped or missing, and writes its results to `test-results/verify/` (`summary.json`, `environment.json`, JUnit and logs; the per-lane evidence stays in `.live-evidence/`). [CONTRIBUTING.md](CONTRIBUTING.md#live-verification) shows how to start them.

### Advanced: debugging lanes

To check only the examples you changed, run the partial lanes. They print a `PARTIAL: ...` line, because a pass from them is not the full verification; only a complete `make verify` is.

```bash
make verify-goldens           # runs every golden-backed example against your local CUBRID (VERIFY_PATHS=<dir> narrows it)
```

`make verify-goldens` stops early with "run `make deps` first" when an example requirement is missing, limits each script to `VERIFY_TIMEOUT` seconds (default 60), and reports each result as pass, mismatch, exec error, timeout, normalizer/read error or skip. The suite lanes (`make verify-web`, `make verify-ai-agent`, …) are listed in [CONTRIBUTING.md](CONTRIBUTING.md#advanced-debugging-lanes).

## Where to go next

| Goal | Start at |
|---|---|
| Copy-and-customize starters | `templates/` |
| JDBC-to-Python migration | `migration/java-to-python/` |
| CUBRIDdb-to-pycubrid driver migration | `migration/cubriddb-to-pycubrid/` |
| Performance patterns | `performance/` |
| Known CUBRID quirks | `pitfalls/`, `KNOWN_ISSUES.md` |
| Supported versions | `SUPPORT_MATRIX.md` |
