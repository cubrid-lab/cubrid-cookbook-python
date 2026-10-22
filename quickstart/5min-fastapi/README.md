# FastAPI + CUBRID quickstart

A small web API that saves items in CUBRID. You start a disposable local
database in Docker, run the API, create an item with an HTTP request, read it
back, then stop and clean up. Everything you need is on this page.

Plan on about 5 minutes once Docker is installed and its images are
downloaded; the first download and build take longer on a slow connection.
New to CUBRID itself? Do [your first CUBRID database from Python](../first-cubrid/README.md)
first: it explains the database, the connector and transactions.

> Korean: [FastAPI 빠른 시작](../../docs/ko/quickstart-fastapi.md)

## What you need

- Linux or macOS with `bash` or `zsh`. On Windows, use a WSL 2 terminal.
- [Docker](https://docs.docker.com/get-docker/) with Compose v2: `docker compose version`
  must print a version.
- `git` and `curl`.
- Python 3.11 or later **only** for way B below (the API on your machine) and
  for the offline tests. Way A needs no Python on your machine.

The CUBRID image is published for x86_64 (`linux/amd64`); on an Apple Silicon
Mac, Docker runs it under emulation. This page was checked on Linux x86_64.

## 1. Get the code

Run these from the folder where you keep projects:

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
cd quickstart/5min-fastapi
```

Every later command on this page runs from this `quickstart/5min-fastapi`
folder. If you open a new terminal, `cd` back into it first.

## 2. Start the database and the API

Choose **one** way. Both serve the API on `http://localhost:8000`, so never run
both at the same time.

| | A. Everything in Docker (recommended) | B. API on your machine |
|---|---|---|
| Database | container `cubrid` | container `cubrid` |
| API | container `api` | `uvicorn` in your terminal, from a Python venv |
| Use it when | you just want to see it work | you want to edit `app.py` and reload |

### A. Everything in Docker (recommended)

```bash
docker compose up -d --build --wait
```

This builds the API image from the `Dockerfile`, starts the database, waits
until its health check passes, then starts the API and waits until it answers.

**Checkpoint.** `docker compose up` returns without an error, and
`docker compose ps` lists both services as `healthy`:

```text
NAME                    IMAGE                COMMAND                  SERVICE   CREATED          STATUS                    PORTS
5min-fastapi-api-1      5min-fastapi-api     "uvicorn app:app --h…"   api       24 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
5min-fastapi-cubrid-1   cubrid/cubrid:11.2   "/entrypoint.sh"         cubrid    25 seconds ago   Up 22 seconds (healthy)   127.0.0.1:33000->33000/tcp
```

The times differ on your machine. Inside Docker, the API reaches the database
by its Compose **service name**, `cubrid`: `docker-compose.yml` sets
`CUBRID_HOST=cubrid` for the `api` container. From your own machine, both
services are at `localhost`, on the ports in the `PORTS` column.

### B. API on your machine, database in Docker

If you already started way A, first stop its API container, which holds port
8000: `docker compose stop api`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d --wait cubrid
uvicorn app:app --reload
```

- The venv keeps the API's packages (`fastapi`, `uvicorn`, `pycubrid`) inside
  this folder. In a new terminal, run `source .venv/bin/activate` again.
- `docker compose up -d --wait cubrid` starts **only** the database and waits
  until its health check passes.
- `uvicorn app:app --reload` runs the API in this terminal and restarts it when
  you save `app.py`. Here the API runs on your machine, so it connects to
  `localhost:33000`, the port Docker publishes for the database: `localhost` is
  the default when `CUBRID_HOST` is not set.

**Checkpoint.** Uvicorn keeps running and prints, after a line naming the
folder it watches:

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [2993868] using StatReload
INFO:     Started server process [2993873]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

The process numbers differ on your machine.

Leave it running and use a second terminal, in the same folder, for step 3.

## 3. Create an item and read it back

The API stores items in its own table, `cookbook_quickstart_items`, which it
creates at startup if it does not exist. An item has a text `val`; the
database assigns its `id`.

First ask the API whether it can reach the database. `GET /health` runs
`SELECT 1 FROM db_root` on a new connection:

```bash
curl -sS localhost:8000/health
```

**Checkpoint.**

```text
{"status":"ok","database":"ok"}
```

If the database does not answer, the same request returns HTTP status `503`
with `{"status":"error","database":"unavailable"}`, and no error details.

Create one item:

```bash
curl -sS -X POST localhost:8000/items -H 'Content-Type: application/json' -d '{"val": "hello from the quickstart"}'
```

**Checkpoint.** On the first run:

```text
{"val":"hello from the quickstart","id":1}
```

Read it back by its `id`:

```bash
curl -sS localhost:8000/items/1
```

```text
{"val":"hello from the quickstart","id":1}
```

`curl -sS localhost:8000/items` lists every item. The `id` is the database's
`AUTO_INCREMENT` value: it is `1` only in a new table. The table keeps its rows
until you drop it (step 4), so a later run returns the next number, for
example `"id":2`; read that `id` back instead. In a browser,
`http://localhost:8000/docs` shows the same API as interactive documentation.

## 4. Stop, run again and clean up

**Stop the API.**

- Way A: `docker compose stop` stops both containers.
- Way B: press Ctrl-C in the Uvicorn terminal, then `docker compose stop`
  stops the database. Run `deactivate` to leave the venv.

**Run it again.** Way A: `docker compose up -d --build --wait`. Way B:
`docker compose up -d --wait cubrid`, then `uvicorn app:app --reload` in the
activated venv. Your items are still there.

**Remove the quickstart's table**, and nothing else, while the database is
running:

```bash
docker compose exec -T cubrid csql -u dba testdb -c "DROP TABLE IF EXISTS cookbook_quickstart_items"
```

It prints `Execute OK.` and `Committed.` with timings. The API creates the
table again the next time it starts.

**Remove the containers.** Choose how much to delete:

| Command | Containers | Data |
|---------|------------|------|
| `docker compose stop` | stopped; `docker compose start` resumes them | kept |
| `docker compose down` | removed | kept in this quickstart's Docker volumes; the next `up` brings it back |
| `docker compose down -v` | removed | **deleted**, including the `testdb` database |

These commands act only on this folder's Compose project, named
`5min-fastapi` after the folder: its two containers, its network and, with
`-v`, its two volumes (`5min-fastapi_cubrid_data`,
`5min-fastapi_cubrid_databases`). They never touch other containers. Way B's
venv is the `.venv` folder; delete it with `rm -rf .venv`.

**Port 33000 is shared.** This quickstart, the
[SQLAlchemy quickstart](../5min-sqlalchemy/README.md) and the repository's root
lab (the `cubrid-cookbook` container) all publish their database on
`127.0.0.1:33000`. Each is a separate Compose project with its own data, so
only one can run at a time. Before you switch, run `docker compose stop` in the
folder of the one you are leaving.

## If something goes wrong

- **`docker: command not found`, or `docker compose version` fails:** install
  Docker with Compose v2 ([Get Docker](https://docs.docker.com/get-docker/)),
  and make sure the Docker daemon is running.
- **`Bind for 127.0.0.1:33000 failed: port is already allocated`** (or
  `8000`): something else holds that port. Find it with
  `docker ps --filter publish=33000` (or `publish=8000`). If it is one of this
  repository's labs, stop it from its own folder with `docker compose stop`;
  otherwise stop the program you started yourself. Do not remove containers or
  volumes you did not create. A failed start leaves this project's containers
  behind; run `docker compose down` here before you try again.
- **Uvicorn stops with `[Errno 98] error while attempting to bind on address
  ('127.0.0.1', 8000): [errno 98] address already in use`** (way B): the API
  container of way A, or another program, holds port 8000. Run
  `docker compose stop api` here, or stop the other program.
- **The database does not become healthy** (`docker compose up --wait`
  reports `unhealthy`, or waits a long time): the first start creates
  `testdb` and can take a minute. Check `docker compose logs cubrid` for the
  reason.
- **`ModuleNotFoundError` or `uvicorn: command not found`** (way B): the venv
  is not active. Run `source .venv/bin/activate`, then
  `python -m pip install -r requirements.txt` again.
- **Uvicorn stops with `pycubrid.exceptions.OperationalError: failed to connect
  to CUBRID broker`** and `Application startup failed`: no database answers on
  `localhost:33000`. Start it with `docker compose up -d --wait cubrid`.
- **A database or login error**: the app connects to the database `testdb` as
  `dba` with an empty password, the settings this Compose file creates. Another
  CUBRID server on port 33000 has different ones; stop it as described above.

More fixes: the [CUBRID quirks and pitfalls](../../pitfalls/README.md) and the
[known issues](../../KNOWN_ISSUES.md).

> **Local only.** The lab's `dba` account has no password, so both ports listen
> on `127.0.0.1` only. Never use these settings for a shared or remote server.

## How the app works

`app.py` creates its table in FastAPI's lifespan startup hook. Blocking database
work runs in a thread, including the synchronous request handlers. Each database
operation commits on success, rolls back on failure, and closes its cursor and
connection. The `?` in its SQL is a parameter placeholder: pycubrid puts each
value into the statement as a safely escaped literal.

## Test without a database

With the venv of way B active:

```bash
python -m pip install -r requirements.txt pytest httpx
python -m pytest tests -q
```

The tests replace the DB-API connection and cover host configuration, startup,
CRUD and `/health` responses, and resource cleanup after database failures.
`tests/test_live.py` is skipped here: it needs a database (next section).

## Test against the database

`tests/test_live.py` runs the same app against a running CUBRID and checks each
answer against the table through a separate connection: `/health` (`200`, and
`503` when the database cannot be reached), creating an item, reading it by
`id` and in the list, `404` for a missing `id`, `422` for an invalid body with
no row written, and a rejected insert that leaves no row. Each test writes only
rows whose `val` starts with its own random `spec03-` marker and deletes them
afterwards, so it never touches your items and can run again.

With the database of step 2 running and the venv active:

```bash
CUBRID_TEST_URL=cubrid+pycubrid://dba@localhost:33000/testdb python -m pytest tests/test_live.py -v
```

The app always connects to port `33000` and database `testdb`, so the URL may
change only the host. Without `CUBRID_TEST_URL` these tests skip; with it set
and no database answering, they fail. From the repository root,
`make spec-03` runs them with `CUBRID_SPEC_GATE=1`, which also turns a missing
URL into a failure, and writes a JUnit report to `.spec-evidence/spec-03.xml`.

## What next?

- **A production-shaped API**, with connection reuse through SQLAlchemy: the
  [FastAPI service template](../../templates/api-service-fastapi/README.md).
- **Core database patterns** (CRUD, transactions, errors): the
  [fundamentals](../../fundamentals/README.md).
- **SQLAlchemy without a web framework**: the
  [SQLAlchemy quickstart](../5min-sqlalchemy/README.md).
