# Lesson 2: Run your first query

Connect to the practice database from Python, send one SQL statement and read
the row it returns. This is lesson 2 of
[your first CUBRID database from Python](README.md).

> Korean: [첫 쿼리 실행하기](../../docs/ko/first-cubrid-first-query.md)

## Before you start

This lesson needs what lesson 1 set up in
[Prepare the lab](README.md#2-prepare-the-lab):

- the lab is running: `python scripts/wait_for_cubrid.py` printed
  `CUBRID is ready: the in-container csql query passed.`;
- you are in the `cubrid-cookbook-python` folder with the virtual environment
  active. In a new terminal, run `cd cubrid-cookbook-python` and
  `source .venv/bin/activate` again.

Every program is a file you run from the terminal; nothing carries over from an
earlier Python session.

## The program

This is the whole first program,
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

## Run it

```bash
python quickstart/first-cubrid/01_first_query.py
```

**Checkpoint.** Expected output:

```text
1 + 1 = 2
Greeting: Hello, CUBRID
Connected to database: testdb
```

If you see `failed to connect to CUBRID broker` instead, the lab is not
running or not ready yet: go back to [Prepare the lab](README.md#2-prepare-the-lab)
and run the readiness check again.

## What the program did

- `pycubrid.connect(...)` opens a **connection**: one session with the server.
  The four settings are the ones from
  [What you are installing](README.md#1-what-you-are-installing).
- `conn.cursor()` gives a **cursor**, which sends SQL with `execute(...)`.
- `fetchone()` returns the next result row as a tuple; `fetchall()` returns all of them.
- `conn.close()` ends the session. The `try`/`finally` closes it even when something fails.

The settings in this file belong to the local-only lab, whose `dba` account
has no password. Never use them for a shared or remote server.

## Next step

Save rows, commit them and read them from another connection:
[lesson 3](save-a-row.md).
