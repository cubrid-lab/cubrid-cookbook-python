# pycubrid Examples

Direct database access using the [pycubrid](https://github.com/cubrid-labs/pycubrid) DB-API 2.0 driver — a pure Python connector for CUBRID with no C dependencies.

## Features

- PEP 249 (DB-API 2.0) compliant — standard Python database interface
- `qmark` parameter style — uses `?` placeholders for safe, parameterized queries
- Full CRUD with `cursor.execute()` and `cursor.executemany()` for batch operations
- Transaction control — `commit()`, `rollback()`, savepoints, and `autocommit` mode
- Large Object support — `CLOB` and `BLOB` via `conn.create_lob()`
- PEP 249 exception hierarchy — `DatabaseError`, `IntegrityError`, `OperationalError`, etc.

## Prerequisites

- Python 3.10+
- CUBRID running on `localhost:33000` with database `testdb`

The root project Docker Compose provides CUBRID. Start from the repository root:

```bash
make up
```

## Setup

```bash
pip install -r requirements.txt
```

## Examples

| File | Topic | Key Concepts |
|------|-------|--------------|
| `01_connect.py` | Connecting to CUBRID | `pycubrid.connect()`, `cursor.description`, server metadata |
| `02_crud.py` | CRUD operations | INSERT/SELECT/UPDATE/DELETE, `executemany()`, `fetchall()` |
| `03_transactions.py` | Transaction control | `commit()`, `rollback()`, savepoints, `autocommit` |
| `04_prepared.py` | Parameterized queries | `qmark` style, SQL injection safety, batch inserts |
| `05_error_handling.py` | Exception handling | PEP 249 exception hierarchy, error recovery |
| `06_lob.py` | Large objects | CLOB/BLOB, `create_lob()`, reading LOB data back |
| `07_merge_upsert.py` | Idempotent sync with MERGE | `MERGE INTO ... USING`, staging tables, deactivate missing rows |
| `08_hierarchy_connect_by.py` | Tree traversal | `CONNECT BY PRIOR`, `START WITH`, `LEVEL`, org charts |
| `09_serial_order_numbers.py` | Business IDs with SERIAL | `CREATE SERIAL`, `NEXT_VALUE`, sequential order numbers |
| `10_collection_columns.py` | Native collection columns | `SET`, `MULTISET`, `LIST` types, inline collection storage |
| `11_bulk_etl_pipeline.py` | Chunked ETL pipeline | staging table, `executemany()` chunks, validation, upsert apply |
| `12_pool_retry_worker.py` | Connection pool & retry | minimal pool, exponential backoff, transient error recovery |
| `13_atomic_counters.py` | Atomic counters | `ON DUPLICATE KEY UPDATE`, hot-path metrics, rankings |
| `14_manual_cascade_delete.py` | App-managed cascades | child-first deletes, preview counts, CUBRID no-CASCADE workaround |

## Run

```bash
python 01_connect.py
python 02_crud.py
python 03_transactions.py
python 04_prepared.py
python 05_error_handling.py
python 06_lob.py
```

Each script is self-contained — it creates its own tables, runs examples, and cleans up.

## Code Highlights

### Connecting to CUBRID

```python
import pycubrid

conn = pycubrid.connect(
    host="localhost",
    port=33000,
    database="testdb",
    user="dba",
    password="",
)
cursor = conn.cursor()
cursor.execute("SELECT 1 + 1 AS result")
print(cursor.fetchone()[0])  # 2
cursor.close()
conn.close()
```

### CRUD with Parameterized Queries

```python
# INSERT — qmark style (? placeholders)
cursor.execute(
    "INSERT INTO cookbook_users (name, email, age) VALUES (?, ?, ?)",
    ("Alice", "alice@example.com", 30),
)

# Batch INSERT with executemany()
users = [("Bob", "bob@example.com", 25), ("Charlie", "charlie@example.com", 35)]
cursor.executemany(
    "INSERT INTO cookbook_users (name, email, age) VALUES (?, ?, ?)",
    users,
)
conn.commit()

# SELECT with filtering
cursor.execute("SELECT name, age FROM cookbook_users WHERE age >= ?", (30,))
for row in cursor.fetchall():
    print(f"  {row[0]}: age {row[1]}")
```

### Large Objects (CLOB/BLOB)

```python
# Store text as CLOB
lob = conn.create_lob("CLOB", "# README\n\nLarge document content here...")
cursor.execute(
    "INSERT INTO cookbook_documents (title, content) VALUES (?, ?)",
    ("README", lob),
)

# Store binary data as BLOB
blob = conn.create_lob("BLOB", b"\x89PNG\r\n...")
cursor.execute(
    "INSERT INTO cookbook_files (filename, data) VALUES (?, ?)",
    ("image.png", blob),
)
conn.commit()
```

## Expected Output

Running `01_connect.py`:

```
=== Basic Connection ===
1 + 1 = 2

=== Connection Info ===
CUBRID version: 11.2.0.0338
Database: testdb
User: DBA

=== Cursor Description ===
Columns:
  id          type_code=8
  name        type_code=2
  value       type_code=6
Row: (1, 'hello', 3.14)
```

Running `02_crud.py`:

```
✓ Created table 'cookbook_users'
✓ Inserted 5 rows

All users (5 rows):
   ID  Name          Email                      Age
  ---  ----          -----                      ---
    1  Alice         alice@example.com           30
    2  Bob           bob@example.com             25
    ...
```

## API Quick Reference

| Method | Description |
|--------|-------------|
| `pycubrid.connect(host, port, database, user, password)` | Open a connection |
| `conn.cursor()` | Create a cursor |
| `conn.commit()` / `conn.rollback()` | Transaction control |
| `conn.close()` | Close the connection |
| `conn.create_lob(lob_type, data)` | Create CLOB or BLOB object |
| `conn.autocommit` | Get/set autocommit mode |
| `cursor.execute(sql, params)` | Execute a single query |
| `cursor.executemany(sql, seq_of_params)` | Execute batch query |
| `cursor.fetchone()` | Fetch one row |
| `cursor.fetchmany(size)` | Fetch `size` rows |
| `cursor.fetchall()` | Fetch all remaining rows |
| `cursor.description` | Column metadata (name, type_code, ...) |
| `cursor.rowcount` | Rows affected by last operation |
| `cursor.lastrowid` | Last AUTO_INCREMENT value |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ConnectionError: Failed to connect` | Ensure CUBRID is running: `make up` from repo root |
| `InterfaceError: Connection closed` | Don't reuse a closed connection — create a new one |
| `IntegrityError: UNIQUE violation` | The row already exists — use UPDATE or ON DUPLICATE KEY UPDATE |
| Parameters not binding | Use `?` placeholders (qmark style), not `%s` or `:name` |

## Learn More

- [pycubrid documentation](https://github.com/cubrid-labs/pycubrid)
- [PEP 249 — DB-API 2.0 Specification](https://peps.python.org/pep-0249/)
- [CUBRID SQL Guide](https://www.cubrid.org/manual/en/11.2/sql/index.html)
