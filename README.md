# CUBRID Python Cookbook

**Production-ready Python examples for CUBRID** — from first connection to production API, with migration guides, performance patterns, and common pitfalls.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CUBRID 11.2](https://img.shields.io/badge/CUBRID-11.2-green.svg)](https://www.cubrid.org/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
![pycubrid](https://img.shields.io/badge/pycubrid-v0.6.0-blue)
![sqlalchemy-cubrid](https://img.shields.io/badge/sqlalchemy--cubrid-v2.1.1-blue)
![status](https://img.shields.io/badge/status-active%20development-yellow)

---

## Get Started

| Your Goal | Go Here | Time |
|-----------|---------|------|
| **Start in 5 minutes** | [`quickstart/5min-fastapi/`](quickstart/5min-fastapi/) | 5 min |
| **Migrate from Java** | [`migration/java-to-python/`](migration/java-to-python/) | 30 min |
| **Build a production API** | [`templates/api-service-fastapi/`](templates/api-service-fastapi/) | 15 min |

---

## What's Inside

### Quickstart

Get a working CUBRID + FastAPI app running with Docker in under 5 minutes.

```bash
cd quickstart/5min-fastapi
docker compose up -d
pip install -r requirements.txt
uvicorn app:app --reload
# Open http://localhost:8000/docs
```

### Migration Guide

Side-by-side Java JDBC → Python migration with real code comparisons. Covers connections, CRUD (DB-API and ORM), transactions, and batch operations.

> CUBRID's JDBC driver and Python driver use the same CAS protocol — zero data migration required.

### Production Templates

Copy-and-customize starting points for real applications:

| Template | Use Case |
|----------|----------|
| [`api-service-fastapi/`](templates/api-service-fastapi/) | REST API with FastAPI, SQLAlchemy, Docker |
| [`async-worker/`](templates/async-worker/) | Background task processing with Celery |
| [`batch-etl/`](templates/batch-etl/) | Data pipeline with Pandas |
| [`dashboard/`](templates/dashboard/) | Interactive dashboard with Streamlit |

### Performance

Benchmark-backed optimization patterns:

| Pattern | Impact |
|---------|--------|
| [Fetch optimization](performance/fetch-optimization/) | SELECT 10K rows: 96ms → 78ms (−19%) |
| [Bulk insert](performance/bulk-insert/) | COMMIT is 7× costlier than INSERT — batch your writes |
| [Connection pooling](performance/connection-pooling/) | Reuse connections to avoid 1.7ms/connect overhead |

### Pitfalls

7 common anti-patterns that cause real production issues — reserved words, auto-commit differences, connection leaks, and more. See [`pitfalls/`](pitfalls/).

### Fundamentals

Step-by-step reference for every core operation:

| Topic | File |
|-------|------|
| [Connecting](fundamentals/connect/) | Basic connection, metadata, context managers |
| [CRUD](fundamentals/crud/) | INSERT, SELECT, UPDATE, DELETE with parameters |
| [Transactions](fundamentals/transactions/) | Commit, rollback, savepoints, auto-commit |
| [Prepared statements](fundamentals/prepared-statements/) | Parameterized queries |
| [Error handling](fundamentals/error-handling/) | Exception types, retry patterns |
| [LOB handling](fundamentals/lob-handling/) | BLOB/CLOB operations |
| [ORM basics](fundamentals/orm-basics/) | SQLAlchemy engine, core, ORM, relationships |

---

## Framework Map

```
pycubrid (DB-API 2.0 driver)
├── Direct usage ─── fundamentals/connect, crud, transactions
├── SQLAlchemy ───── fundamentals/orm-basics, templates/api-service-fastapi
├── FastAPI ──────── quickstart/5min-fastapi, templates/api-service-fastapi
├── Celery ──────── templates/async-worker
├── Pandas ──────── templates/batch-etl
└── Streamlit ───── templates/dashboard
```

## Connection

All examples connect to the same CUBRID instance:

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `33000` |
| Database | `testdb` |
| User | `dba` |
| Password | *(empty)* |

```python
# pycubrid (direct)
import pycubrid
conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")

# SQLAlchemy
from sqlalchemy import create_engine
engine = create_engine("cubrid+pycubrid://dba@localhost:33000/testdb")
```

Start the database:
```bash
docker compose up -d
```

## Project Structure

```
cubrid-cookbook-python/
├── quickstart/
│   └── 5min-fastapi/          # Docker + FastAPI in 5 minutes
├── migration/
│   └── java-to-python/        # JDBC → pycubrid/SQLAlchemy migration
├── templates/
│   ├── api-service-fastapi/   # Production REST API
│   ├── async-worker/          # Celery background tasks
│   ├── batch-etl/             # Pandas data pipeline
│   └── dashboard/             # Streamlit dashboard
├── performance/
│   ├── fetch-optimization/    # SELECT tuning (benchmarked)
│   ├── bulk-insert/           # Write batching (benchmarked)
│   └── connection-pooling/    # Pool configuration
├── pitfalls/                  # 7 common anti-patterns
├── fundamentals/
│   ├── connect/               # Connection basics
│   ├── crud/                  # CRUD operations
│   ├── transactions/          # Transaction management
│   ├── prepared-statements/   # Parameterized queries
│   ├── error-handling/        # Exception patterns
│   ├── lob-handling/          # BLOB/CLOB
│   └── orm-basics/            # SQLAlchemy ORM
└── docker-compose.yml         # CUBRID 11.2
```

## Related Projects

- [pycubrid](https://github.com/cubrid-labs/pycubrid) — Pure Python DB-API 2.0 driver for CUBRID
- [sqlalchemy-cubrid](https://github.com/cubrid-labs/sqlalchemy-cubrid) — SQLAlchemy 2.0 dialect for CUBRID
- [CUBRID](https://www.cubrid.org/) — The CUBRID database

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for planned additions.

For the ecosystem-wide view, see the [CUBRID Labs Ecosystem Roadmap](https://github.com/cubrid-labs/.github/blob/main/ROADMAP.md) and [Project Board](https://github.com/orgs/cubrid-labs/projects/2).

## Contributing

PRs welcome! Each example should be self-contained and independently runnable. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE)
