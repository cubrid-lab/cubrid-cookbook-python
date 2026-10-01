# Pitfalls & Anti-Patterns

Common mistakes when working with CUBRID + Python, and how to avoid them.

## 1. Creating a New Connection Per Request

**Problem**: Each connection costs ~1.66ms. At scale this adds up fast and may exhaust server connection limits.

```python
# ❌ Anti-pattern — new connection on every request
@app.get("/items")
def list_items():
    conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")
    cursor = conn.cursor()
    cursor.execute("SELECT id, val FROM cookbook_items")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()  # Connection destroyed, never reused
    return rows
```

**Fix**: Use a connection pool via SQLAlchemy or a shared connection manager.

```python
# ✅ Correct — connection pool reuses connections
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    "cubrid+pycubrid://dba@localhost:33000/testdb",
    pool_size=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)


@app.get("/items")
def list_items():
    with SessionLocal() as session:
        # Session returns connection to pool on exit
        return session.execute(text("SELECT id, val FROM cookbook_items")).all()
```

See: [performance/connection-pooling/](../performance/connection-pooling/)

---

## 2. N+1 Query Problem

**Problem**: Loading related objects in a loop fires one query per parent row.

```python
# ❌ Anti-pattern — 1 query for categories + N queries for items
categories = session.execute(select(CookbookCategory)).scalars().all()
for cat in categories:
    print(cat.name, len(cat.items))  # Each access triggers a lazy-load query
```

**Fix**: Use `joinedload` or `selectinload` to prefetch relationships.

```python
from sqlalchemy.orm import selectinload

# ✅ Correct — 2 queries total (1 for categories, 1 for all items)
stmt = select(CookbookCategory).options(selectinload(CookbookCategory.items))
categories = session.execute(stmt).scalars().all()
for cat in categories:
    print(cat.name, len(cat.items))  # Already loaded, no extra query
```

| Strategy | Queries | Use When |
|----------|---------|----------|
| `selectinload` | 2 (parent + children via IN) | Default choice, works well for most cases |
| `joinedload` | 1 (single JOIN) | Small result sets, single child relationship |
| `subqueryload` | 2 (parent + subquery) | Complex filters on parent query |

---

## 3. Committing Per Row in Batch Operations

**Problem**: COMMIT is the most expensive operation (~47ms). Per-row commits make batch inserts ~70× slower.

```python
# ❌ Anti-pattern — COMMIT per row (10K rows ≈ 470 seconds)
for i in range(10000):
    cursor.execute("INSERT INTO cookbook_logs (msg) VALUES (?)", (f"log_{i}",))
    conn.commit()  # 47ms × 10,000 = 470 seconds
```

**Fix**: Batch your commits.

```python
# ✅ Correct — COMMIT per batch (10K rows ≈ 12 seconds)
BATCH_SIZE = 1000
for batch_start in range(0, 10000, BATCH_SIZE):
    for i in range(batch_start, min(batch_start + BATCH_SIZE, 10000)):
        cursor.execute("INSERT INTO cookbook_logs (msg) VALUES (?)", (f"log_{i}",))
    conn.commit()  # 47ms × 10 = 0.47 seconds total
```

See: [performance/bulk-insert/](../performance/bulk-insert/)

---

## 4. Using CUBRID Reserved Words as Column Names

**Problem**: CUBRID reserves many common words — for example `key`, `value`, `count`, `data`, `date`, `day`, `level`, `size` and `user`. Using one as an unquoted column name fails with a syntax error that often points at the *next* token rather than the reserved word itself.

```python
# ❌ Fails — both "key" and "value" are CUBRID reserved words
cursor.execute("CREATE TABLE cookbook_settings (key VARCHAR(50), value VARCHAR(255))")
# pycubrid.ProgrammingError: ... Syntax error: unexpected 'VARCHAR' ...
```

Renaming only `value` is not enough: `(key VARCHAR(50), val VARCHAR(255))` is rejected in the same way, because `key` is reserved too.

**Fix**: Rename every reserved column to a non-reserved name.

```python
# ✅ Correct — no reserved words left in the DDL
cursor.execute("CREATE TABLE cookbook_settings (setting_key VARCHAR(50), val VARCHAR(255))")
```

| Reserved Word | Replacement |
|--------------|-------------|
| `key` | `setting_key` (or another descriptive `*_key`) |
| `value` | `val` |
| `count` | `cnt` |
| `data` | `file_data` |
| `date` / `day` | `created_date` / `metric_day` |

If a reserved name is unavoidable (for example, an existing schema), quote it with double quotes, square brackets or backticks — CUBRID accepts all three — and quote it in every statement that uses it:

```python
cursor.execute('CREATE TABLE cookbook_settings ("key" VARCHAR(50), "value" VARCHAR(255))')
cursor.execute('INSERT INTO cookbook_settings ("key", "value") VALUES (?, ?)', ("theme", "dark"))
```

`name` is **not** a reserved word and can be used unquoted. Check candidate names against the official reserved-word list for your server version: [CUBRID 11.2](https://www.cubrid.org/manual/en/11.2/sql/keyword.html), [CUBRID 11.4](https://www.cubrid.org/manual/en/11.4/sql/keyword.html). SQLAlchemy's CUBRID dialect quotes reserved words in generated DDL automatically; see [KNOWN_ISSUES.md](../KNOWN_ISSUES.md#2-reserved-word-column-names).

Every statement in this section is checked against a live server by [`reserved-words/01_reserved_words.py`](reserved-words/01_reserved_words.py) (`make verify`, CUBRID 11.2 and 11.4 in CI).

---

## 5. SQL String Interpolation

**Problem**: Building queries with f-strings or `%` formatting opens the door to SQL injection and type errors.

```python
# ❌ Anti-pattern — SQL injection vulnerability
user_input = "'; DROP TABLE cookbook_items; --"
cursor.execute(f"SELECT * FROM cookbook_items WHERE val = '{user_input}'")
```

**Fix**: Always use parameterized queries.

```python
# ✅ Correct — parameterized query (pycubrid uses ? placeholders)
cursor.execute("SELECT * FROM cookbook_items WHERE val = ?", (user_input,))

# ✅ Correct — SQLAlchemy ORM (automatically parameterized)
stmt = select(CookbookItem).where(CookbookItem.val == user_input)
session.execute(stmt)
```

---

## 6. Blocking Sync Operations in Async Context

**Problem**: The classic DB-API entry points — `pycubrid.connect()` and its connection/cursor methods, and the legacy `CUBRIDdb` driver — are synchronous. Calling them directly in an `async def` handler blocks the event loop for every network round trip.

```python
# ❌ Anti-pattern — sync DB call in async handler blocks the event loop
@app.get("/items")
async def list_items():
    conn = pycubrid.connect(...)  # Blocks event loop
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cookbook_items")  # Blocks event loop
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows
```

**Fix**: Use a native async driver in async code, or keep the synchronous driver out of the event loop.

```python
# ✅ Option A — native asyncio driver: pycubrid.aio
import pycubrid.aio


@app.get("/items")
async def list_items():
    conn = await pycubrid.aio.connect(host="localhost", port=33000, database="testdb", user="dba")
    try:
        cur = conn.cursor()
        await cur.execute("SELECT id, val FROM cookbook_items")
        rows = await cur.fetchall()
        await cur.close()
        return rows
    finally:
        await conn.close()


# ✅ Option B — SQLAlchemy async engine on top of pycubrid.aio
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("cubrid+aiopycubrid://dba@localhost:33000/testdb")


# ✅ Option C — sync handler (FastAPI runs it in a thread pool)
@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.execute(text("SELECT * FROM cookbook_items")).all()


# ✅ Option D — explicit thread offload for existing sync code in an async handler
import asyncio


@app.get("/items")
async def list_items():
    return await asyncio.to_thread(sync_fetch_items)
```

Options A and B are demonstrated end to end in [fundamentals/async/](../fundamentals/async/), whose `requirements.txt` pins the tested floors: `pycubrid >= 1.6.0`, `sqlalchemy-cubrid >= 1.4.2` (the release this cookbook requires for the `cubrid+aiopycubrid://` dialect) and `sqlalchemy[asyncio]`.

> **Recommendation**: In an asyncio application, use `pycubrid.aio` or the `cubrid+aiopycubrid://` engine. With synchronous code, keep handlers synchronous (FastAPI threads them automatically) or offload the call to a thread — never call the sync API directly inside `async def`.

---

## 7. Forgetting to Close Cursors and Connections

**Problem**: Unclosed cursors/connections leak resources and may exhaust the connection pool or server limits.

```python
# ❌ Anti-pattern — exception before close() leaks resources
conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")
cursor = conn.cursor()
cursor.execute("SELECT * FROM cookbook_items")
rows = cursor.fetchall()
# If an exception occurs here, close() is never called
process(rows)
cursor.close()
conn.close()
```

**Fix**: Use context managers or try/finally.

```python
# ✅ Correct — try/finally guarantees cleanup
conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")
try:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM cookbook_items")
        rows = cursor.fetchall()
        process(rows)
    finally:
        cursor.close()
finally:
    conn.close()

# ✅ Better — SQLAlchemy Session handles this automatically
with SessionLocal() as session:
    result = session.execute(text("SELECT * FROM cookbook_items"))
    process(result.all())
# Session and connection automatically returned to pool
```

---

## Quick Reference

| Pitfall | Impact | Difficulty to Fix |
|---------|--------|-------------------|
| Connection per request | High (throughput) | Easy (add pool) |
| N+1 queries | High (latency) | Medium (eager loading) |
| Per-row COMMIT | High (throughput) | Easy (batch) |
| Reserved words | Medium (errors) | Easy (rename) |
| SQL interpolation | Critical (security) | Easy (parameterize) |
| Sync in async | High (throughput) | Easy (`pycubrid.aio` or sync handlers) |
| Unclosed resources | Medium (leaks) | Easy (context managers) |
