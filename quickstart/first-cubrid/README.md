# Your first CUBRID database from Python

**New to CUBRID? Start here.** This tutorial is for you if you can run a Python
file but have never used CUBRID. You start a disposable practice database on
your own machine, connect to it from Python, save a few rows, see what
`commit` and `rollback` do, and clean up. You do not need FastAPI, SQLAlchemy
or any of this repository's contributor tools.

Plan on about 15 minutes once the prerequisites are installed. The first
download of the database image takes longer on a slow connection.

> Korean: [첫 CUBRID 튜토리얼](../../docs/ko/first-cubrid.md)

The tutorial has five short lessons, in this order:

1. [What you are installing](#1-what-you-are-installing) and
   [Prepare the lab](#2-prepare-the-lab), on this page.
2. [Run your first query](first-query.md).
3. [Save rows and read them back](save-a-row.md).
4. [Undo a change with rollback](rollback.md).
5. [Finish safely](finish.md): clean up, recover and stop the lab.

## 1. What you are installing

Two separate things:

- **The CUBRID database server.** It stores the data. Here it runs in a Docker
  container, a throwaway "lab" that you can stop or delete at any time.
- **pycubrid, the Python connector.** It is a Python package that talks to a
  running server. Installing it does **not** install or start a server, and it
  does not create a database.

To connect, Python needs four facts about the server:

| Setting | Value in this lab | Meaning |
|---------|-------------------|---------|
| host | `localhost` | the machine the server runs on (yours) |
| port | `33000` | the network port of the server's **broker**, the entry point that accepts connections |
| database | `testdb` | the database the lab creates when it first starts |
| user / password | `dba` / empty | the administrator account of the lab |

> **Local only.** The lab's `dba` account has no password, so the lab listens
> on `127.0.0.1` only: nothing outside your machine can reach it. Never use an
> empty password, or these settings, for a shared or remote server.

## 2. Prepare the lab

**What you need**

- Linux or macOS with `bash` or `zsh`. On Windows, use a WSL 2 terminal.
- [Docker](https://docs.docker.com/get-docker/) with Compose v2: `docker compose version`
  must print a version.
- Python 3.11 or later: `python3 --version`.
- `git`.

The CUBRID 11.4 image is published for x86_64 (`linux/amd64`). On an Apple
Silicon Mac, Docker runs it under emulation; this tutorial was checked on
Linux x86_64 only.

**Get the code and a Python environment.** Run these from the folder where
you keep projects. Every later command runs from the `cubrid-cookbook-python`
folder that `git clone` creates.

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r quickstart/first-cubrid/requirements.txt
```

`source .venv/bin/activate` makes `python` mean this project's own Python, so
packages install here and nowhere else. If you open a new terminal later, run
`cd cubrid-cookbook-python` and `source .venv/bin/activate` again.

**Start the database and wait until it is ready.**

```bash
CUBRID_VERSION=11.4 docker compose up -d
python scripts/wait_for_cubrid.py
```

`docker compose up -d` starts a container named `cubrid-cookbook` from
`docker-compose.yml` and returns at once; the database needs a few more
seconds to start. The second command waits for that.

**Checkpoint.** The last line must be:

```text
CUBRID is ready: the in-container csql query passed.
```

`docker compose ps` should then list `cubrid-cookbook` with
`127.0.0.1:33000->33000/tcp`. Its status may still read `health: starting`
for up to 30 seconds after the database answers; that is normal.

If the wait times out, run `docker compose logs cubrid` to see why. If
`docker compose up` reports that port 33000 is already in use, another
program, often another CUBRID container, holds it: stop that program first.
Do not delete containers or volumes you did not create.

Next: [run your first query](first-query.md).

## 3. First success: connect and read a value

This step has its own lesson: [Lesson 2: Run your first query](first-query.md)
runs `01_first_query.py`, shows its output and explains the connection and
cursor it uses.

## 4. Save data, commit it and check it from another connection

This step is now two lessons: [Lesson 3: Save rows and read them back](save-a-row.md)
runs `02_save_and_verify.py`, and [Lesson 4: Undo a change with rollback](rollback.md)
runs `03_rollback.py`.

## 5. Finish, recover and run it again

Cleaning up the tutorial's table, recovering from an interrupted run and
stopping the lab are in [Lesson 5: Finish safely](finish.md).

## What next?

- **More SQL with pycubrid**: the [pycubrid fundamentals](../../fundamentals/pycubrid/README.md)
  go on to CRUD, prepared statements, errors, LOBs and more, on the same lab.
- **Python objects instead of SQL text**: the [SQLAlchemy quickstart](../5min-sqlalchemy/README.md).
- **A small web API**: the [FastAPI quickstart](../5min-fastapi/README.md).

For how connections, the broker and transactions work in more depth, see the
[pycubrid documentation](https://github.com/cubrid-lab/pycubrid#readme).
