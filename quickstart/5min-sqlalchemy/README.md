# SQLAlchemy + CUBRID quickstart

One Python script that writes, reads, updates and deletes rows in CUBRID with
SQLAlchemy, first with SQLAlchemy Core (SQL expressions), then with the ORM
(Python classes mapped to tables). You start a disposable local database in
Docker, run the script, and clean up. Everything you need is on this page.

Plan on about 5 minutes once Docker and Python are installed and the database
image is downloaded; the first download takes longer on a slow connection.
New to CUBRID itself? Do [your first CUBRID database from Python](../first-cubrid/README.md)
first: it explains the database, the connector and transactions.

> Korean: [SQLAlchemy 빠른 시작](../../docs/ko/quickstart-sqlalchemy.md)

## What you need

- Linux or macOS with `bash` or `zsh`. On Windows, use a WSL 2 terminal.
- [Docker](https://docs.docker.com/get-docker/) with Compose v2: `docker compose version`
  must print a version.
- Python 3.11 or later on your machine: `python3 --version`. The script runs
  on your machine; only the database runs in Docker.
- `git`.

The CUBRID image is published for x86_64 (`linux/amd64`); on an Apple Silicon
Mac, Docker runs it under emulation. This page was checked on Linux x86_64.

## 1. Get the code and a Python environment

Run these from the folder where you keep projects:

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
cd quickstart/5min-sqlalchemy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Every later command on this page runs from this `quickstart/5min-sqlalchemy`
folder, with the venv active. The venv keeps the packages (`sqlalchemy`,
`sqlalchemy-cubrid` and the `pycubrid` driver) inside this folder. If you open a
new terminal, run `cd` back into the folder and `source .venv/bin/activate`
again.

## 2. Start the database

```bash
docker compose up -d --wait
```

This starts one container from `docker-compose.yml`, which creates the database
`testdb`, and waits until its health check (a `SELECT 1` inside the container)
passes.

**Checkpoint.** `docker compose up` returns without an error, and
`docker compose ps` lists the database as `healthy`:

```text
NAME                       IMAGE                COMMAND            SERVICE   CREATED          STATUS                    PORTS
5min-sqlalchemy-cubrid-1   cubrid/cubrid:11.2   "/entrypoint.sh"   cubrid    17 seconds ago   Up 16 seconds (healthy)   127.0.0.1:33000->33000/tcp
```

The times differ on your machine. The script runs on your machine, so it
connects to `localhost:33000`, the port Docker publishes for the database
(`PORTS` column).

## 3. Run the script

```bash
python app.py
```

**Checkpoint.** Expected output:

```text
=== SQLAlchemy Core CRUD ===
Core query result: [(1, 'core-sample', 'v1')]

=== SQLAlchemy ORM CRUD ===
ORM query result: 1 orm-sample

Done. Core and ORM CRUD completed successfully.
```

What happened, in [`app.py`](app.py):

- It connects with the URL `cubrid+pycubrid://dba@localhost:33000/testdb`:
  the `cubrid` SQLAlchemy dialect with the `pycubrid` driver, as user `dba`
  with an empty password, to the database `testdb` on `localhost:33000`.
- It creates two tables of its own, `cookbook_core_items` and
  `cookbook_orm_items`. The Core part inserts the row `core-sample` and reads it
  back as the tuple `(item_id, item_name, val)`, then updates and deletes it.
  The ORM part does the same with a `CookbookOrmItem` object and prints its
  `item_id` and `item_name`.
- On exit, even after an error, it drops both tables again.

Because the script creates both tables new each time, the ids are `1` on
every run, and you can run `python app.py` again at once with the same output.
It drops any existing tables with these two names, so run it only against a
database where those names are not used for anything else, such as this one.

## 4. Stop, run again and clean up

The script leaves no tables behind. To stop the database, choose how much to
delete:

| Command | The container | Data |
|---------|---------------|------|
| `docker compose stop` | stopped; `docker compose start` resumes it | kept |
| `docker compose down` | removed | kept in this quickstart's Docker volumes; the next `docker compose up -d --wait` brings it back |
| `docker compose down -v` | removed | **deleted**, including the `testdb` database |

To run it again later, start the database with `docker compose up -d --wait`,
then run `python app.py`.

These commands act only on this folder's Compose project, named
`5min-sqlalchemy` after the folder: its container, its network and, with
`-v`, its two volumes (`5min-sqlalchemy_cubrid_data`,
`5min-sqlalchemy_cubrid_databases`). They never touch other containers. Run
`deactivate` to leave the venv, and `rm -rf .venv` to delete it.

**Port 33000 is shared.** This quickstart, the
[FastAPI quickstart](../5min-fastapi/README.md) and the repository's root lab
(the `cubrid-cookbook` container) all publish their database on
`127.0.0.1:33000`. Each is a separate Compose project with its own data, so
only one can run at a time. Before you switch, run `docker compose stop` in the
folder of the one you are leaving.

## If something goes wrong

- **`docker: command not found`, or `docker compose version` fails:** install
  Docker with Compose v2 ([Get Docker](https://docs.docker.com/get-docker/)),
  and make sure the Docker daemon is running.
- **`Bind for 127.0.0.1:33000 failed: port is already allocated`**: something
  else holds port 33000. Find it with `docker ps --filter publish=33000`. If it
  is one of this repository's labs, stop it from its own folder with
  `docker compose stop`; otherwise stop the program you started yourself. Do
  not remove containers or volumes you did not create. A failed start leaves
  this project's container behind; run `docker compose down` here before you
  try again.
- **The database does not become healthy** (`docker compose up --wait`
  reports `unhealthy`, or waits a long time): the first start creates
  `testdb` and can take a minute. Check `docker compose logs cubrid` for the
  reason.
- **`ModuleNotFoundError: No module named 'sqlalchemy'`**, or
  `Can't load plugin: sqlalchemy.dialects:cubrid.pycubrid`: the venv is not
  active. Run `source .venv/bin/activate`, then
  `python -m pip install -r requirements.txt` again.
- **`Database operation failed: (pycubrid.exceptions.OperationalError) failed
  to connect to CUBRID broker`**, followed by two `Cleanup failed:` lines: no
  database answers on `localhost:33000`. Start it with `docker compose up -d --wait`.
- **A database or login error**: the script connects to `testdb` as `dba` with
  an empty password, the settings this Compose file creates. Another CUBRID
  server on port 33000 has different ones; stop it as described above.

More fixes: the [CUBRID quirks and pitfalls](../../pitfalls/README.md) and the
[known issues](../../KNOWN_ISSUES.md).

> **Local only.** The lab's `dba` account has no password, so the database
> listens on `127.0.0.1` only. Never use these settings for a shared or remote
> server.

## What next?

- **More SQLAlchemy with CUBRID** (relationships, bulk inserts, upserts,
  reflection, collection types): the
  [SQLAlchemy recipes](../../fundamentals/sqlalchemy/README.md).
- **A production-shaped batch job** with pandas and SQLAlchemy: the
  [batch ETL template](../../templates/batch-etl/README.md).
- **A web API**: the [FastAPI quickstart](../5min-fastapi/README.md).
