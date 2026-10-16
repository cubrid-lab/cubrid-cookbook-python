# Lesson 3: Save rows and read them back

Create a small table of the tutorial's own, save two rows, commit them and read
them from a second connection. This is lesson 3 of
[your first CUBRID database from Python](README.md).

> Korean: [행 저장하고 다시 읽기](../../docs/ko/first-cubrid-save-a-row.md)

## Before you start

- [Lesson 2](first-query.md) printed `Connected to database: testdb`, so the
  lab is running and the connection settings work;
- you are in the `cubrid-cookbook-python` folder with the virtual environment
  active. In a new terminal, run `cd cubrid-cookbook-python` and
  `source .venv/bin/activate` again.

## The program

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

## Run it

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

## If you run it again

The table from the first run is still there, so the script stops without
changing anything:

- `cookbook_first_cubrid_notes is left over from an earlier run.` means the
  tutorial's own table exists. Clean it up with
  [lesson 5](finish.md#clean-up-the-tutorials-table), then run this lesson again.
- `A table named cookbook_first_cubrid_notes already exists and was not created by this tutorial.`
  means the table belongs to someone else. The tutorial changes nothing and
  will not drop it.

## Next step

Undo a change before it is saved: [lesson 4, rollback](rollback.md).
