# Lesson 5: Finish safely

Remove the tutorial's table, recover from an interrupted or repeated run, and
stop the lab without deleting more than you mean to. This is lesson 5 of
[your first CUBRID database from Python](README.md).

> Korean: [안전하게 마치기](../../docs/ko/first-cubrid-finish.md)

## Before you start

- You can run this lesson at any time after [lesson 3](save-a-row.md), also
  when a lesson stopped half way;
- you are in the `cubrid-cookbook-python` folder with the virtual environment
  active. In a new terminal, run `cd cubrid-cookbook-python` and
  `source .venv/bin/activate` again.

## Clean up the tutorial's table

[`04_cleanup.py`](04_cleanup.py) drops `cookbook_first_cubrid_notes` only if
this tutorial created it, so it is safe to run at any time, as often as you
like.

```bash
python quickstart/first-cubrid/04_cleanup.py
```

**Checkpoint.** Expected output:

```text
Dropped cookbook_first_cubrid_notes.
```

Run it again and it prints `Nothing to clean up: cookbook_first_cubrid_notes does not exist.`
If a table of that name exists but this tutorial did not create it, the script
prints `cookbook_first_cubrid_notes was not created by this tutorial; it was left unchanged.`
and drops nothing.

## Run the tutorial again

After the cleanup, start again at [lesson 2](first-query.md). The database
keeps running between runs.

## If a lesson was interrupted

If you pressed Ctrl-C, or the terminal closed:

- Interrupted before its commit, a lesson saved nothing; run it again.
- If lesson 3 prints `cookbook_first_cubrid_notes is left over from an earlier run.`, run
  `04_cleanup.py`, then lesson 3 again.
- If it prints `A table named cookbook_first_cubrid_notes already exists and was not
  created by this tutorial.`, that table belongs to someone else; the tutorial
  changes nothing and will not drop it.
- If the database itself stopped, run `CUBRID_VERSION=11.4 docker compose up -d`
  and `python scripts/wait_for_cubrid.py` again.

## Stop the lab

Choose how much to remove; run these from `cubrid-cookbook-python`:

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
