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

**Problem**: CUBRID reserves common words like `value`, `count`, `data`, and `name`. Using them as column names causes cryptic SQL errors.

```python
# ❌ Fails — "value" is a CUBRID reserved word
cursor.execute("CREATE TABLE cookbook_settings (key VARCHAR(50), value VARCHAR(255))")
# Error: Syntax error or unexpected token
```

**Fix**: Use alternative names.

```python
# ✅ Correct — use non-reserved alternatives
cursor.execute("CREATE TABLE cookbook_settings (key VARCHAR(50), val VARCHAR(255))")
```

| Reserved Word | Replacement |
|--------------|-------------|
| `value` | `val` |
| `count` | `cnt` |
| `data` | `file_data` |
| `name` | `item_name` (or backtick-quote if unavoidable) |

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

**Problem**: CUBRID's Python drivers (pycubrid, CUBRIDdb) are synchronous. Calling them directly in an async handler blocks the event loop.

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

**Fix**: Either use sync handlers (FastAPI runs them in a thread pool automatically) or use `run_in_executor`.

```python
# ✅ Option A — sync handler (FastAPI auto-threads it)
@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.execute(text("SELECT * FROM cookbook_items")).all()


# ✅ Option B — explicit thread pool for async handler
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=5)


@app.get("/items")
async def list_items():
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(executor, sync_fetch_items)
    return rows
```

> **Recommendation**: Use sync handlers with FastAPI for CUBRID. It's simpler and FastAPI handles threading automatically.

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
| Sync in async | High (throughput) | Easy (sync handlers) |
| Unclosed resources | Medium (leaks) | Easy (context managers) |
