# Fetch Optimization

Patterns for efficiently processing large SELECT result sets.

## Problem

As row count increases, Python-side parsing time grows proportionally
(historical figures, pycubrid 0.5.0+16a8634, CUBRID 11.2, undated):

```
100 rows:   fetch 0.03ms  (1.4% of total)
1000 rows:  fetch 6.46ms  (59.9% of total)
10000 rows: fetch 81.33ms (83.0% of total)
```

## Solutions

### 1. SELECT Only Needed Columns

```python
# ❌ Bad — parses every column including unused ones
cursor.execute("SELECT * FROM cookbook_orders")

# ✅ Good — only parse what you need
cursor.execute("SELECT order_id, total_amt FROM cookbook_orders")
```

### 2. fetchall() vs fetchone() Loop

```python
# fetchone() loop — one Python call per row
rows = []
while True:
    row = cursor.fetchone()
    if row is None:
        break
    rows.append(row)

# fetchall() — one call, returns the whole result as a list
cursor.execute("SELECT order_id, total_amt FROM cookbook_orders")
rows = cursor.fetchall()
```

> Measured on pycubrid 1.10.0 (CUBRID 11.4.6, 2026-10-09, median of 5 runs, 10K rows x 5 columns):
> `fetchall()` 52 ms vs `fetchone()` loop 52 ms (50-225 ms; the first run was cold). On 1.10.0 there is
> no measurable speed difference, so choose `fetchall()` for simplicity and `fetchmany()`/`yield_per`
> to bound memory. The earlier "19% faster than a `fetchone()` loop" claim (pycubrid 0.5.0) no longer holds.

### 3. Server-Side Pagination

```python
# Don't fetch 100K rows at once — paginate on the server
PAGE_SIZE = 1000


def fetch_page(cursor, offset: int, limit: int) -> list:
    cursor.execute(
        "SELECT order_id, total_amt FROM cookbook_orders ORDER BY order_id LIMIT ?, ?",
        (offset, limit),
    )
    return cursor.fetchall()


# Usage
page = fetch_page(cursor, offset=0, limit=PAGE_SIZE)
```

### 4. SQLAlchemy Equivalents

```python
from sqlalchemy import select
from app.models import CookbookOrder

# ❌ Bad — loads full ORM objects with all columns
stmt = select(CookbookOrder)
results = session.execute(stmt).scalars().all()

# ✅ Good — fetch only needed columns as tuples
stmt = select(CookbookOrder.order_id, CookbookOrder.total_amt)
results = session.execute(stmt).all()

# ✅ Better — yield_per for memory efficiency on huge result sets
stmt = select(CookbookOrder).execution_options(yield_per=1000)
for row in session.execute(stmt).scalars():
    process(row)
```

## Running the Benchmark

`benchmark.py` connects to `localhost:33000`, database `testdb`, user `dba` with an empty password,
which is what the repository's `docker-compose.yml` provides. From the repository root:

```bash
CUBRID_VERSION=11.4 docker compose up -d --wait cubrid   # CUBRID 11.4 on localhost:33000, database testdb
pip install pycubrid
python performance/fetch-optimization/benchmark.py
docker compose down                    # stop the database when finished
```

The script creates and fills `cookbook_fetch_test` (10,000 rows), prints the time of each fetch strategy and the number of rows it fetched (10,000 each), and takes about 15 seconds. It drops `cookbook_fetch_test` when it finishes, also when a step fails. `make spec-12` runs it as a live test (see [Testing the benchmarks](../README.md#testing-the-benchmarks)).

## Benchmark Reference

- pycubrid 1.10.0 (2026-10-09, median of 5): 10K rows, 5 columns `fetchall()` 52 ms; 2 columns 28 ms
- pycubrid 1.12.0 (2026-10-13, median of 5, same host): `fetchmany(500)` loop over the 5 columns 49 ms (47–77).
  It replaces the earlier `SELECT *` measurement, which ran the same query as the 5-column `fetchall()`.
- Historical (pycubrid 0.5.0+16a8634): SELECT 10K fetch 96ms → 78ms after optimization (−19%)
- Full details: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)
