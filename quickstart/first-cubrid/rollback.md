# Lesson 4: Undo a change with rollback

Insert one more row, see it inside the open transaction, then discard it with
`rollback()`. This is lesson 4 of
[your first CUBRID database from Python](README.md).

> Korean: [rollback으로 변경 되돌리기](../../docs/ko/first-cubrid-rollback.md)

## Before you start

- [Lesson 3](save-a-row.md) printed its two rows, so the tutorial table
  `cookbook_first_cubrid_notes` exists with two committed rows;
- you are in the `cubrid-cookbook-python` folder with the virtual environment
  active. In a new terminal, run `cd cubrid-cookbook-python` and
  `source .venv/bin/activate` again.

## The program

[`03_rollback.py`](03_rollback.py) inserts one more row, shows it inside its
open transaction, then calls **`rollback()`**, which discards everything since
the last commit. Your two saved rows stay.

## Run it

```bash
python quickstart/first-cubrid/03_rollback.py
```

**Checkpoint.** Expected output:

```text
Rows before the change: 2
Rows inside the open transaction: 3
Rows after rollback: 2
```

## What happened

- Inside the open transaction, your own connection already sees the third row.
- `rollback()` ends the transaction and discards the row. The two rows from
  lesson 3 stay, because they were committed.
- Each script closes its connections before it exits. An open transaction,
  even one that only read data, holds locks: a later `DROP TABLE` from another
  connection would wait for it.

You can run this lesson again: it adds and discards the same extra row each
time.

If it prints `The tutorial table cookbook_first_cubrid_notes is missing: run 02_save_and_verify.py first.`,
do [lesson 3](save-a-row.md) first.

## Next step

Clean up and stop the lab safely: [lesson 5](finish.md).
