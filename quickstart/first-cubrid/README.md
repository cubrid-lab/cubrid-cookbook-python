# Your first CUBRID database from Python

**New to CUBRID? Start here.** This tutorial is for you if you can run a Python
file but have never used CUBRID. You start a disposable practice database on
your own machine, connect to it from Python, save a few rows, see what
`commit` and `rollback` do, and clean up. You do not need FastAPI, SQLAlchemy
or any of this repository's contributor tools.

Plan on about 15 minutes once the prerequisites are installed. The first
download of the database image takes longer on a slow connection.

> Korean: [첫 CUBRID 튜토리얼](../../docs/ko/first-cubrid.md)

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

## 3. First success: connect and read a value

Here is the whole first program,
[`quickstart/first-cubrid/01_first_query.py`](01_first_query.py):

```python
"""01_first_query.py — connect to CUBRID from Python and read a first result.

Step 3 of the beginner tutorial (quickstart/first-cubrid/README.md).
"""

from __future__ import annotations

import pycubrid

# The disposable lab started by docker-compose.yml: a local-only database with
# an empty password for the dba account. Never use these settings for a shared
# or remote server.
SETTINGS = {
    "host": "localhost",  # the machine running the lab container
    "port": 33000,  # the broker port: the connection entry point
    "database": "testdb",  # the database the lab image creates
    "user": "dba",
    "password": "",
}


def main() -> None:
    conn = pycubrid.connect(**SETTINGS)  # open a connection to the database
    try:
        cursor = conn.cursor()  # a cursor sends SQL and holds its results
        cursor.execute("SELECT 1 + 1, 'Hello, CUBRID'")
        total, greeting = cursor.fetchone()  # one row, as a tuple
        print(f"1 + 1 = {total}")
        print(f"Greeting: {greeting}")

        cursor.execute("SELECT database()")
        print(f"Connected to database: {cursor.fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- `pycubrid.connect(...)` opens a **connection**: one session with the server.
- `conn.cursor()` gives a **cursor**, which sends SQL with `execute(...)`.
- `fetchone()` returns the next result row as a tuple; `fetchall()` returns all of them.
- `conn.close()` ends the session. The `try`/`finally` closes it even when something fails.

Run it:

```bash
python quickstart/first-cubrid/01_first_query.py
```

**Checkpoint.** Expected output:

```text
1 + 1 = 2
Greeting: Hello, CUBRID
Connected to database: testdb
```

## 4. Save data, commit it and check it from another connection

[`02_save_and_verify.py`](02_save_and_verify.py) creates a table of its own,
`cookbook_first_cubrid_notes`, and saves two rows. It marks the table with a comment,
so later steps only ever touch this table. If a table with that name already
exists, it stops without changing anything.

The important lines:

```python
cursor.execute(
    "CREATE TABLE cookbook_first_cubrid_notes ("
    " id INT AUTO_INCREMENT PRIMARY KEY,"
    " note VARCHAR(100) NOT NULL"
    ") COMMENT = 'created by the cubrid-cookbook first-cubrid tutorial'"
)
for note in ("My first row", "My second row"):
    cursor.execute("INSERT INTO cookbook_first_cubrid_notes (note) VALUES (?)", (note,))
conn.commit()
```

- The `?` is a **parameter placeholder**. You pass the values as a separate
  Python argument, and pycubrid puts each one into the statement as a properly
  escaped value, so a value can never change the meaning of the statement.
  Always pass values this way instead of pasting them into the SQL text
  yourself. (How pycubrid binds values: [parameterized queries](../../fundamentals/parameterized-queries/README.md).)
- Changes are not permanent until you call **`commit()`**. pycubrid starts with
  autocommit off: everything since the last commit forms one **transaction**.
  `commit()` makes the new table and both rows durable and visible to other
  connections.

After the commit, the script opens a **second, independent connection** and
reads the table, the way another program would.

```bash
python quickstart/first-cubrid/02_save_and_verify.py
```

**Checkpoint.** Expected output:

```text
Created cookbook_first_cubrid_notes and saved 2 rows.
A second connection reads:
  1: My first row
  2: My second row
```

The ids `1` and `2` come from `AUTO_INCREMENT` on a new table.

**Undo a change with rollback.** [`03_rollback.py`](03_rollback.py) inserts
one more row, shows it inside its open transaction, then calls
**`rollback()`**, which discards everything since the last commit. Your two
saved rows stay.

```bash
python quickstart/first-cubrid/03_rollback.py
```

**Checkpoint.** Expected output:

```text
Rows before the change: 2
Rows inside the open transaction: 3
Rows after rollback: 2
```

Each script closes its connections before it exits. An open transaction,
even one that only read data, holds locks: a later `DROP TABLE` from another
connection would wait for it.

## 5. Finish, recover and run it again

**Clean up the tutorial's table.** [`04_cleanup.py`](04_cleanup.py) drops
`cookbook_first_cubrid_notes` only if this tutorial created it, so it is safe to run at
any time, as often as you like.

```bash
python quickstart/first-cubrid/04_cleanup.py
```

**Checkpoint.** Expected output:

```text
Dropped cookbook_first_cubrid_notes.
```

Run it again and it prints `Nothing to clean up: cookbook_first_cubrid_notes does not exist.`

**Run the tutorial again.** After the cleanup, start again at step 3. The
database keeps running between runs.

**If a step was interrupted** (you pressed Ctrl-C, or the terminal closed):

- Interrupted before its commit, a step saved nothing; run it again.
- If step 4 prints `cookbook_first_cubrid_notes is left over from an earlier run.`, run
  `04_cleanup.py`, then step 4 again.
- If it prints `A table named cookbook_first_cubrid_notes already exists and was not
  created by this tutorial.`, that table belongs to someone else; the tutorial
  changes nothing and will not drop it.
- If the database itself stopped, run `CUBRID_VERSION=11.4 docker compose up -d`
  and `python scripts/wait_for_cubrid.py` again.

**Stop the lab.** Choose how much to remove; run these from
`cubrid-cookbook-python`:

| Command | The container | Your data |
|---------|---------------|-----------|
| `docker compose stop` | stopped; `docker compose start` resumes it | kept |
| `docker compose down` | removed | kept in the lab's Docker volumes; the next `CUBRID_VERSION=11.4 docker compose up -d` brings it back |
| `docker compose down -v` | removed | **deleted**, including `testdb` itself |

`docker compose down -v` deletes only this lab's volumes, the ones
`docker-compose.yml` names. It does not touch other containers or volumes. To
leave the Python environment, run `deactivate`.

## What next?

- **More SQL with pycubrid**: the [pycubrid fundamentals](../../fundamentals/pycubrid/README.md)
  go on to CRUD, prepared statements, errors, LOBs and more, on the same lab.
- **Python objects instead of SQL text**: the [SQLAlchemy quickstart](../5min-sqlalchemy/README.md).
- **A small web API**: the [FastAPI quickstart](../5min-fastapi/README.md).

For how connections, the broker and transactions work in more depth, see the
[pycubrid documentation](https://github.com/cubrid-lab/pycubrid#readme).
