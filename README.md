# CUBRID Python Cookbook

**Production-ready Python examples for CUBRID** — from first connection to production API, with migration guides, performance patterns, and common pitfalls.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CUBRID 11.2 | 11.4](https://img.shields.io/badge/CUBRID-11.2%20%7C%2011.4-green.svg)](SUPPORT_MATRIX.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
![pycubrid](https://img.shields.io/badge/pycubrid-%E2%89%A51.6.1-blue)
![sqlalchemy-cubrid](https://img.shields.io/badge/sqlalchemy--cubrid-%E2%89%A51.6.0-blue)
![status](https://img.shields.io/badge/status-active%20development-yellow)

---

## Get Started

| Your Goal | Go Here | Time |
|-----------|---------|------|
| **Start in 5 minutes** | [`quickstart/5min-fastapi/`](quickstart/5min-fastapi/) | 5 min |
| **Start with SQLAlchemy** | [`quickstart/5min-sqlalchemy/`](quickstart/5min-sqlalchemy/) | 5 min |
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
| [`api-service-fastapi/`](templates/api-service-fastapi/) | REST API with FastAPI, SQLAlchemy, Docker (12 recipes) |
| [`flask/`](templates/flask/) | Flask + Flask-SQLAlchemy patterns (11 recipes) |
| [`django/`](templates/django/) | Minimal Django app on CUBRID |
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
| [Parameterized queries](fundamentals/parameterized-queries/) | Safe parameter binding (client-side, not server-side prepare) |
| [Error handling](fundamentals/error-handling/) | Exception types, retry patterns |
| [LOB handling](fundamentals/lob-handling/) | BLOB/CLOB operations |
| [ORM basics](fundamentals/orm-basics/) | SQLAlchemy engine, core, ORM, relationships |
| [pycubrid driver](fundamentals/pycubrid/) | 16 DB-API recipes: cursors, fetch sizing, batch error handling |
| [SQLAlchemy recipes](fundamentals/sqlalchemy/) | 7 recipes including SET/MULTISET/SEQUENCE collection types |
| [Pandas](fundamentals/pandas/) | 6 recipes: read_sql, chunked reads, to_sql load patterns |
| [Async I/O](fundamentals/async/) | pycubrid.aio and SQLAlchemy async engine |
| [Alembic migrations](fundamentals/alembic/) | Programmatic migration setup with CubridImpl |
| [JSON type CRUD](fundamentals/json/) | Native JSON columns, JSON_EXTRACT/UNQUOTE patterns |
| [Isolation levels](fundamentals/isolation-levels/) | 3 MVCC levels, no-dirty-read demonstration |

---

## Framework Map

```
pycubrid (DB-API 2.0 driver)
├── Direct usage ─── fundamentals/connect, crud, transactions, pycubrid
├── SQLAlchemy ───── fundamentals/orm-basics, sqlalchemy, quickstart/5min-sqlalchemy
├── FastAPI ──────── quickstart/5min-fastapi, templates/api-service-fastapi
├── Flask ─────────── templates/flask
├── Django ────────── templates/django
├── Celery ──────── templates/async-worker
├── Pandas ──────── fundamentals/pandas, templates/batch-etl
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
│   ├── 5min-fastapi/          # Docker + FastAPI in 5 minutes
│   └── 5min-sqlalchemy/       # Docker + SQLAlchemy in 5 minutes
├── migration/
│   └── java-to-python/        # JDBC → pycubrid/SQLAlchemy migration
├── templates/
│   ├── api-service-fastapi/   # Production REST API (12 recipes)
│   ├── flask/                 # Flask + Flask-SQLAlchemy (11 recipes)
│   ├── django/                # Minimal Django app
│   ├── async-worker/          # Celery background tasks
│   ├── batch-etl/             # Pandas data pipeline
│   └── dashboard/             # Streamlit dashboard (5 recipes)
├── performance/
│   ├── fetch-optimization/    # SELECT tuning (benchmarked)
│   ├── bulk-insert/           # Write batching (benchmarked)
│   └── connection-pooling/    # Pool configuration
├── pitfalls/                  # 7 common anti-patterns
├── fundamentals/
│   ├── connect/               # Connection basics
│   ├── crud/                  # CRUD operations
│   ├── transactions/          # Transaction management
│   ├── parameterized-queries/   # Parameterized queries
│   ├── error-handling/        # Exception patterns
│   ├── lob-handling/          # BLOB/CLOB
│   ├── orm-basics/            # SQLAlchemy ORM
│   ├── pycubrid/              # 16 pycubrid DB-API recipes
│   ├── sqlalchemy/            # 7 SQLAlchemy recipes
│   ├── pandas/                # 6 Pandas recipes
│   ├── async/                 # pycubrid.aio + async SQLAlchemy
│   ├── alembic/               # Programmatic Alembic migrations
│   ├── json/                  # Native JSON column CRUD
│   └── isolation-levels/      # 3 MVCC isolation levels
└── docker-compose.yml         # CUBRID 11.2
```

## Related Projects

- [pycubrid](https://github.com/cubrid-lab/pycubrid) — Pure Python DB-API 2.0 driver for CUBRID
- [sqlalchemy-cubrid](https://github.com/cubrid-lab/sqlalchemy-cubrid) — SQLAlchemy 2.0 dialect for CUBRID
- [CUBRID](https://www.cubrid.org/) — The CUBRID database

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) for planned additions.

For the ecosystem-wide view, see the [CUBRID Labs Ecosystem Roadmap](https://github.com/cubrid-lab/.github/blob/main/ROADMAP.md) and [Project Board](https://github.com/orgs/cubrid-lab/projects/2).

## Contributing

PRs welcome! Each example should be self-contained and independently runnable. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE)
