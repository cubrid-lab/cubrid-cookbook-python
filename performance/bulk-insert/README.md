# Bulk Insert Patterns

Strategies for efficiently inserting large volumes of data.

## Problem

A single-row INSERT + COMMIT costs ~47ms for the COMMIT alone.
Inserting 10,000 rows with individual COMMITs takes **~470 seconds** (7.8 minutes).

## Solutions

### 1. Batch COMMIT

```python
"""Reduce transaction overhead by committing in batches."""
from __future__ import annotations

import pycubrid

BATCH_SIZE = 1000

conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS cookbook_bulk_test (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        val INT
    )
""")
conn.commit()

# Insert 10,000 rows with COMMIT every 1,000 rows
for batch_start in range(0, 10000, BATCH_SIZE):
    for i in range(batch_start, min(batch_start + BATCH_SIZE, 10000)):
        cursor.execute(
            "INSERT INTO cookbook_bulk_test (name, val) VALUES (?, ?)",
            (f"item_{i}", i),
        )
    conn.commit()  # One COMMIT per batch

cursor.close()
conn.close()
```

**Performance comparison:**

| Strategy | 10K rows | COMMIT count |
|----------|----------|-------------|
| Per-row COMMIT | ~477s | 10,000 |
| 1000-row batch | ~12s | 10 |
| Single COMMIT | ~7s | 1 |

> ⚠️ A single COMMIT risks full rollback on failure. Batching is safer in production.

### 2. executemany

```python
"""Insert multiple rows in a single call."""
from __future__ import annotations

import pycubrid

conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")
cursor = conn.cursor()

data = [(f"item_{i}", i) for i in range(1000)]

cursor.executemany(
    "INSERT INTO cookbook_bulk_test (name, val) VALUES (?, ?)",
    data,
)
conn.commit()

cursor.close()
conn.close()
```

### 3. SQLAlchemy Bulk Insert

```python
"""Bulk insert using SQLAlchemy Core (faster than ORM object creation)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

engine = create_engine("cubrid+pycubrid://dba@localhost:33000/testdb")

# Insert via Core — skips ORM object instantiation for maximum speed
with Session(engine) as session:
    session.execute(
        CookbookBulkTest.__table__.insert(),
        [{"name": f"item_{i}", "val": i} for i in range(10000)],
    )
    session.commit()
```

## Key Insight

COMMIT cost is **7× more expensive** than the INSERT itself (47ms vs 7ms).
Reducing COMMIT frequency is the single most effective optimization for write-heavy workloads.

## Benchmark Reference

- INSERT execute: 7.10ms, COMMIT: 51.32ms
- Full details: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)
