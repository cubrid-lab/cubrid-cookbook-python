# CUBRIDdb to pycubrid Migration Guide

This guide moves a Python application from the official C-extension driver,
`CUBRIDdb` ([CUBRID/cubrid-python](https://github.com/CUBRID/cubrid-python)), to the
pure-Python driver [`pycubrid`](https://github.com/cubrid-lab/pycubrid). It is a
driver-to-driver migration inside Python. To move a **Java/JDBC** application to Python,
use the [Java to Python migration guide](../java-to-python/) instead.

Both drivers implement Python DB-API 2.0 (PEP 249) and talk to the same CUBRID broker,
so the database, schema, data and most SQL text stay as they are. They are **not**
interchangeable: they differ in installation, connection arguments, the default
transaction mode, thread sharing, how parameters reach the server, error attributes and
the native CCI features they expose. Treat the move as an application change that you
test, not as swapping one import for another. pycubrid does not claim full CCI or
`_cubrid` parity.

## How the claims on this page were checked

| Label | Meaning |
|-------|---------|
| **Run here** | Executed by the four recipes in this directory against live CUBRID; their output is the golden in [`expected/`](expected/). |
| **pycubrid source** | Read in the installed pycubrid package (1.13.1, and 1.6.1 for the floor) or in its changelog. |
| **Official source, not run** | Read in [cubrid-python `v11.3.0.51`](https://github.com/CUBRID/cubrid-python/tree/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5) (commit `c63ab9c`, `VERSION` 11.3.0). The cookbook does not build or run the official driver, so its runtime behavior is **unverified** here. |

No official-driver comparison run exists in this repository. Every CUBRIDdb statement on
this page comes from reading its source, and the CUBRIDdb snippets below are not executed.

## File overview

| File | What it shows |
|------|---------------|
| [01_connection_mapping.py](01_connection_mapping.py) | DSN → keyword arguments, autocommit OFF by default, opting into autocommit, cursor and connection closing, the module's `threadsafety` |
| [02_parameterized_crud.py](02_parameterized_crud.py) | `?` parameters with `str`, `Decimal`, `date`, `bytes` and `None`; `executemany()`; a hostile string stored as plain text; `rowcount` |
| [03_fetch_and_errors.py](03_fetch_and_errors.py) | `description`, tuple rows and dicts built from them, `fetchone/fetchmany/fetchall`, a CLOB column, `errno`/`code`/`sqlstate`/`args`, `InterfaceError` |
| [04_transaction_visibility.py](04_transaction_visibility.py) | What a second session sees before and after `commit()`/`rollback()`, a failed statement inside a transaction, and the same steps with autocommit ON |

Each recipe creates its own table (`cookbook_cdb_connect`, `cookbook_cdb_orders`,
`cookbook_cdb_events`, `cookbook_cdb_ledger`) with a marker comment. It stops without
changing anything when a table with that name exists without the marker, drops a marked
table left over from an interrupted run, and drops its own table in a `finally` block.

## Run the recipes

Start the cookbook lab first (`make up` from the repository root, see
[GETTING_STARTED.md](../../GETTING_STARTED.md)), then:

```bash
cd migration/cubriddb-to-pycubrid
pip install -r requirements.txt
python 01_connection_mapping.py
python 02_parameterized_crud.py
python 03_fetch_and_errors.py
python 04_transaction_visibility.py
```

Compare all four with their goldens from the repository root:

```bash
make verify-goldens VERIFY_PATHS=migration/cubriddb-to-pycubrid
```

`make verify` (CUBRID 11.2 and 11.4 in CI) runs the same goldens. `make test` checks
offline that every recipe has a golden, that the tables use the `cookbook_` prefix and
that this page's links and commands resolve.

The recipes need `pycubrid>=1.6.1`, the cookbook's global floor; their output was the
same on pycubrid 1.6.1 and 1.13.1. Features that need a newer pycubrid are named with
their version below and are not used by the recipes.

## 1. Installation

| | CUBRIDdb (official) | pycubrid |
|---|---|---|
| What it is | C extension (`_cubrid`) over the bundled CCI library, plus the `CUBRIDdb` wrapper package | Pure Python; no compiler or CCI library |
| Install | Build from a pinned source revision: `git clone --recursive`, check out the tag, then the build commands in its [README](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/README.md) (a setuptools build, or a wheel built from the checkout and then installed) | `pip install pycubrid` |
| Type hints | No `py.typed` or `.pyi` stubs in the source tree | Ships `py.typed` (pycubrid source) |
| asyncio | No async API in the source tree | `pycubrid.aio` (since pycubrid 1.1.0) |

Pin the official driver to a source revision you have tested, such as tag `v11.3.0.51`
(the revision this page cites). Do **not** use `pip install CUBRID-Python` as a stand-in
for it: the newest release of that PyPI project is 9.3.0, a source archive uploaded on
2014-05-15 (PyPI metadata, checked 2026-10-24), years older than the 11.3 sources.
The official README also mentions prebuilt wheels on `ftp.cubrid.org`; this guide did not
check them.

## 2. Connection mapping

CUBRIDdb, before (official source, not run):

```python
import CUBRIDdb

conn = CUBRIDdb.connect("CUBRID:localhost:33000:testdb:::", "dba", "")
print(conn.autocommit)  # True: the extension enables autocommit on connect
cur = conn.cursor()  # conn.cursor(dictCursor=True) for dict rows
cur.execute("UPDATE cookbook_cdb_ledger SET balance = ? WHERE id = ?", (10, 1))
# committed already
cur.close()
conn.close()
```

pycubrid, after (run here, `01_connection_mapping.py`):

```python
import pycubrid

conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba", password="")
print(conn.autocommit)  # False
with conn.cursor() as cur:  # the cursor is closed when the block ends
    cur.execute("UPDATE cookbook_cdb_ledger SET balance = ? WHERE id = ?", (10, 1))
conn.commit()  # without this the update is rolled back on close
conn.close()
```

| Topic | CUBRIDdb (official source, not run) | pycubrid |
|-------|-------------------------------------|----------|
| Arguments | `connect(dsn, user, password)`, a CCI URL `CUBRID:host:port:db:::`; `Connection(..., charset="utf8")` | `connect(host=, port=, database=, user=, password=, ...)` keyword arguments; no URL and no CCI URL properties (an unknown keyword only warns, pycubrid source) |
| Default user | `"public"` ([`connections.py:17`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/connections.py#L17)) | `"dba"` (pycubrid source). Always pass `user=` explicitly |
| Autocommit after connect | ON: `cci_set_autocommit(..., CCI_AUTOCOMMIT_TRUE)` in connection init ([`python_cubrid.c:464`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/cubrid_ext/python_cubrid.c#L464)) | OFF (**run here**); `connect(autocommit=True)` or `conn.autocommit = True` to opt in |
| Commit / rollback | `conn.commit()`, `conn.rollback()` | Same names; required while autocommit is OFF. DDL is transactional too while autocommit is OFF, so commit a `CREATE TABLE` before relying on it |
| Charset | `charset` argument, default `"utf8"` | `charset=` argument since pycubrid 1.9.0, default `"utf-8"` (pycubrid changelog); older releases always use UTF-8 |
| `threadsafety` | `2`: threads may share connections ([`__init__.py:11`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/__init__.py#L11)) | `1`: threads may share the module, **not** a connection (**run here**). Give each thread its own connection or use a pool |
| `paramstyle` | `'qmark'` | `'qmark'` (**run here**) |
| Closed objects | not checked here | Using a closed cursor or connection raises `InterfaceError` (**run here**) |

The one-session check in `01_connection_mapping.py` inserts a row with autocommit OFF and
counts it twice: the same session sees its pending row, a second connection does not,
and after `rollback()` neither does. With autocommit ON the second connection sees the
row at once, which is the behavior CUBRIDdb code was written against.

## 3. Safe parameterized CRUD

Keep the `?` markers and pass values as a tuple. The SQL text does not change.

| Python value | CUBRIDdb wrapper (official source, not run) | Ordinary pycubrid cursor |
|---|---|---|
| any | `prepare()` then `bind_param()` per value, sent as a CCI typed bind ([`cursors.py:143`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L143)) | Rendered by the driver into an escaped SQL literal, then one prepare-and-execute request (pycubrid source) |
| `None` | Skipped by `_bind_params` (no bind call, [`cursors.py:183`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L183)); what CCI then sends was not run here | SQL `NULL` (**run here**); `WHERE col = ?` with `None` matches nothing, use `IS NULL` |
| `Decimal`, `date`, `bytes`, `str` | Bound by type (`bytes` as `VARBIT`) | Stored and read back as `Decimal`, `datetime.date`, `bytes`, `str` (**run here**) |
| `executemany()` | Prepares once, then binds and executes each row ([`cursors.py:255`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L255)) | For INSERT/UPDATE/DELETE/MERGE: every row rendered as a literal statement and sent in one batch request; `rowcount` is the total (**run here**) |

Driver-side literal conversion is why the hostile value in `02_parameterized_crud.py`
(`O'Reilly'); DROP TABLE ...; --`) is stored as text and the table survives. The protection
covers only values passed through `?`. Never put untrusted values into the SQL string with
f-strings, `%` or `.format()`; identifiers such as table names cannot be parameters, so
check them against a fixed list.

**Opt-in prepared batch.** pycubrid 1.12.0 added `cursor.executemany(sql, rows,
prepared=True)` for INSERT, UPDATE, DELETE and MERGE: one `PREPARE` and one
`EXECUTE_ARRAY` request with typed host variables instead of rendered literals (pycubrid
changelog). Consider it for large write batches after measuring your own workload; other
statement types raise `NotSupportedError`. A failing row is undone on its own while the
other rows run, so keep the transaction OFF autocommit and decide on `commit()` or
`rollback()` yourself. The recipes do not use it because they keep the 1.6.1 floor.

```python
# pycubrid >= 1.12.0 only; not executed by the recipes
cur.executemany(
    "INSERT INTO cookbook_cdb_orders (customer, amount) VALUES (?, ?)",
    rows,
    prepared=True,
)
conn.commit()
```

## 4. Fetching and error handling

**Rows.** CUBRIDdb chooses the row shape with `conn.cursor(dictCursor=True)` (official
source). An ordinary pycubrid cursor always returns tuples; build a dict from
`cursor.description` when you need one (**run here**):

```python
cur.execute("SELECT id, title FROM cookbook_cdb_events ORDER BY id")
names = [column[0] for column in cur.description]
rows = [dict(zip(names, row)) for row in cur.fetchall()]
```

`description` entries are 7-tuples, and the type code compares equal to `pycubrid.NUMBER`,
`pycubrid.STRING`, `pycubrid.DATETIME` and the other DB-API type objects (**run here**).
Do not rely on the `null_ok` field across pycubrid versions: 1.6.1 and 1.13.1 reported it
differently in this guide's checks.

**LOB columns.** An ordinary pycubrid cursor returns a BLOB or CLOB value as a LOB handle
(a `dict`), not as the content (**run here**). Read it with `pycubrid.Lob` as in
[`fundamentals/pycubrid/06_lob.py`](../../fundamentals/pycubrid/06_lob.py), or `CAST` a short
CLOB to `VARCHAR` in SQL. CUBRIDdb's `_cubrid` LOB object API (`connection.lob()`,
`cursor.fetch_lob()`, `lob.read/write/seek/imports/export`) has no ordinary pycubrid
counterpart.

**Errors.** The PEP 249 class names are the same; what the exception carries is not.

| | CUBRIDdb (official source, not run) | pycubrid |
|---|---|---|
| `exc.args` | `(error_code, "ERROR: DBMS, <code>, <message>")` ([`python_cubrid.c:294-301`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/cubrid_ext/python_cubrid.c#L294-L301)) | `(message,)` (**run here**) |
| Error number | `exc.args[0]` | `exc.errno`, also `exc.code` on database errors: `-670` for a duplicate key, `-493` for an unknown table or a syntax error (**run here**) |
| SQLSTATE | none | `exc.sqlstate`, for example `'23000'` for the duplicate key (**run here**). Some SQLSTATEs changed between pycubrid releases (the unknown-table case is `42S02` on 1.6.1 and `42000` on 1.13.1), so branch on `errno` or the exception class |
| Exception class | chosen from a fixed list of codes in `handle_error` | `IntegrityError`, `ProgrammingError`, `OperationalError`, ... (**run here** for the first two) |

Code that unpacks `code, message = exc.args` must change to `exc.errno` and `str(exc)`.
`InterfaceError` (closed cursor or connection) is a `pycubrid.Error` but not a
`DatabaseError` and has no `errno` (**run here**).

**Transaction failures.** A failed statement does not end the transaction: rows written
earlier in it stay pending until you call `commit()` or `rollback()`
(`04_transaction_visibility.py`, **run here**). With autocommit ON, each earlier statement
is already committed and `rollback()` cannot undo it; that is the situation CUBRIDdb code
is in by default.

**Disconnects and unknown outcomes.** When the connection drops while a `commit()` (or an
autocommit statement) is in flight, the client cannot know whether the server applied it.
Do not blindly retry a non-idempotent write after an `OperationalError`: reconnect, check
the data (for example by a unique business key), then decide. The recipes do not simulate
a disconnect.

**Deliberately unsupported on ordinary pycubrid cursors.** CCI-level APIs that the
`_cubrid` module exposes, such as explicit `prepare()`/`bind_param()`, the native LOB
object, `connection.set()` collection binding, `escape_string()`, result positioning and
HA URL properties, are not part of the ordinary DB-API surface. pycubrid has an opt-in
`pycubrid.compat.cubriddb` / `pycubrid.compat.native` namespace (constructors since 1.8.0,
CUBRIDdb-style tuple and dict cursors since 1.9.0) that covers a bounded subset of them;
its own [compatibility document](https://github.com/cubrid-lab/pycubrid/blob/99b98a13eb18d8a85312fcafc620acb1f608ece8/docs/UPSTREAM_COMPATIBILITY.md)
lists what is delivered and what is not. It is not a drop-in replacement, and the recipes
here do not use it.

## 5. Decision points

**Keep CUBRIDdb** when the application depends on native-only functionality listed above
that the opt-in pycubrid namespace does not cover, or when a workload you have measured
is faster on it and that difference matters to you.

**Consider pycubrid** when you want a pure-Python install with no compiler or CCI build,
type hints (`py.typed`), native asyncio (`pycubrid.aio`), or SQLAlchemy through
[`sqlalchemy-cubrid`](https://github.com/cubrid-lab/sqlalchemy-cubrid).

**Performance.** This guide quotes no performance numbers, because results depend on the
driver versions, server, workload and machine. Dated measurements that compare the two
drivers are in cubrid-benchmark (pinned at commit `edf8836`), each with its environment
and caveats:

- [pycubrid-release-baseline](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-release-baseline),
  run `2026-10-11_main-vs-1.10.0-vs-cubriddb`: pycubrid `main` and 1.10.0 against CUBRIDdb
  v11.3.0.51 on CUBRID 11.4.6.
- [pycubrid-executemany-overhead](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-executemany-overhead),
  run `2026-10-11_executemany-vs-cubriddb`: `executemany()` paths of both drivers; its
  README says the run was on a shared, loaded machine and that only pooled medians are
  reliable.
- [pycubrid-prepared-batch](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-prepared-batch):
  prepared batch paths of pycubrid on CUBRID 10.2-11.4.

Measure your own workload on your own server before deciding on performance grounds. The
cookbook's [performance patterns](../../performance/) measure pycubrid alone.

## Migration checklist

- [ ] Install pycubrid (`pip install pycubrid`) and remove the CUBRIDdb build from the
      deployment only after the application passes its tests on pycubrid.
- [ ] Replace each `CUBRIDdb.connect("CUBRID:host:port:db:::", user, password)` with
      `pycubrid.connect(host=, port=, database=, user=, password=)`, passing `user=`
      explicitly.
- [ ] Decide the transaction mode per connection: add `commit()`/`rollback()` where code
      relied on CUBRIDdb's autocommit ON, or pass `autocommit=True` deliberately.
- [ ] Stop sharing one connection between threads; use one connection per thread or a pool.
- [ ] Keep every value in `?` parameters; remove any string-built SQL.
- [ ] Replace `cursor(dictCursor=True)` with dicts built from `cursor.description`.
- [ ] Replace `exc.args[0]` error-code checks with `exc.errno` or the exception class.
- [ ] Rework LOB code to `pycubrid.Lob` and check every native `_cubrid` call against the
      unsupported list above.
- [ ] Run your own tests, and these recipes, against your CUBRID version.
