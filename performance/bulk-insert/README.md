# Bulk Insert Patterns

Strategies for efficiently inserting large volumes of data.

## Problem

Each INSERT + COMMIT round trip costs ~36 ms (pycubrid 1.10.0, CUBRID 11.4.6, 2026-10-09, median of 5 runs;
range 29-39 ms), i.e. ~28 rows/s. Inserting 10,000 rows with individual COMMITs would take about 6 minutes.

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

Measured with `benchmark.py` on pycubrid 1.10.0 / CUBRID 11.4.6 (2026-10-09), median of 5 runs
(min-max), i5-9400F, Python 3.12:

| Strategy | Rows | Time | Throughput (rows/s) |
|----------|------|------|---------------------|
| Per-row COMMIT | 500 | 17.98 s (14.54-19.64) | 28 (25-34) |
| COMMIT every 500 rows | 5,000 | 3.91 s (3.60-4.65) | 1,279 (1,075-1,388) |
| Single COMMIT | 5,000 | 3.39 s (3.36-3.84) | 1,477 (1,301-1,489) |

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

On pycubrid 1.10.0 a per-row INSERT + COMMIT ran at ~28 rows/s versus ~1,279 rows/s with a COMMIT every 500 rows (about 45x).
Reducing COMMIT frequency is the single most effective optimization for write-heavy workloads.

## Benchmark Reference

- pycubrid 1.10.0 (2026-10-09): see the table above; INSERT + COMMIT ~36 ms per row; 10K-row per-row-COMMIT time (~357 s) is extrapolated from the 500-row run
- Historical (pycubrid 0.5.0+16a8634, CUBRID 11.2): INSERT execute 7.10ms, COMMIT 51.32ms
- Full details: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)
