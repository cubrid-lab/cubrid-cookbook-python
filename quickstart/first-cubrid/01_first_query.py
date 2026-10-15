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
