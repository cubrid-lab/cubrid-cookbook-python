# Connection Pooling

Patterns for reducing connection creation overhead through pooling and reuse.

## Problem

CUBRID connection creation costs **~1.66ms** (after optimization).
In a web application creating a new connection per request:
- At 1000 req/s → 1.66 seconds spent on connection creation alone
- Actual impact is worse due to GC, TCP handshake overhead, etc.

## Solutions

### 1. SQLAlchemy Connection Pool (Recommended)

```python
"""Use SQLAlchemy's built-in connection pool."""

from __future__ import annotations

from sqlalchemy import create_engine, text

engine = create_engine(
    "cubrid+pycubrid://dba@localhost:33000/testdb",
    pool_size=5,  # Number of connections to keep in the pool
    max_overflow=10,  # Extra connections allowed beyond pool_size
    pool_timeout=30,  # Max seconds to wait for a connection
    pool_recycle=3600,  # Recreate connections after 1 hour (handles CUBRID idle timeout)
    pool_pre_ping=True,  # Validate connections before use
)

# First request: creates connection (~1.66ms)
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))

# Second request: reuses from pool (~0.01ms)
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
```

### 2. FastAPI + SQLAlchemy Integration

```python
"""Per-request session management in FastAPI."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

engine = create_engine(
    "cubrid+pycubrid://dba@localhost:33000/testdb",
    pool_size=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)

app = FastAPI()


def get_db() -> Generator[Session, None, None]:
    """Provide a session per request, return to pool on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # Returns connection to pool (does NOT destroy it)


@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT * FROM cookbook_items"))
    return [dict(row._mapping) for row in result]
```

### 3. Pool Size Guidelines

| App Type | pool_size | max_overflow | Rationale |
|----------|-----------|-------------|-----------|
| Small API (< 100 req/s) | 5 | 10 | Defaults are sufficient |
| Medium API (100–1000 req/s) | 10 | 20 | Headroom for concurrent requests |
| Batch processing | 2 | 0 | Sequential processing, minimize idle connections |
| Dashboard / analytics | 3 | 5 | Intermittent queries, keep pool small |

### 4. pool_recycle Setting (Important)

CUBRID server disconnects idle connections after `session_state_timeout`.
Set `pool_recycle` shorter than the server timeout to avoid stale connections.

```python
# CUBRID default session_state_timeout: 21600s (6 hours)
# Set pool_recycle well below that (safety margin)
engine = create_engine(
    "cubrid+pycubrid://dba@localhost:33000/testdb",
    pool_recycle=3600,  # 1 hour — 1/6 of server timeout
    pool_pre_ping=True,  # Detect broken connections before use
)
```

## Benchmark Reference

- Connection creation: 1.66ms (optimized from 2.24ms, **−26%**)
- Full details: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)
