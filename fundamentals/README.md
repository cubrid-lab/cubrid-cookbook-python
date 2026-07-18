# Fundamentals

Core database patterns using pycubrid (DB-API 2.0) and SQLAlchemy ORM.

Start here if you're new to CUBRID + Python.

## Sections

| Section | Description | Driver |
|---------|-------------|--------|
| [connect/](./connect/) | Basic connection, metadata, cursor usage | pycubrid |
| [crud/](./crud/) | Create, Read, Update, Delete operations | pycubrid |
| [transactions/](./transactions/) | Commit, rollback, isolation levels | pycubrid |
| [parameterized-queries/](./parameterized-queries/) | Parameterized queries for safety and performance | pycubrid |
| [error-handling/](./error-handling/) | Connection failures, constraint violations, timeouts | pycubrid |
| [lob-handling/](./lob-handling/) | Large Object (BLOB/CLOB) operations | pycubrid |
| [orm-basics/](./orm-basics/) | SQLAlchemy engine, Core, ORM, relationships, reflection | SQLAlchemy |

## Prerequisites

```bash
# Start CUBRID via Docker
docker compose up -d

# Install Python driver
pip install pycubrid

# (Optional) Install SQLAlchemy dialect
pip install sqlalchemy-cubrid
```

## Connection Info

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `33000` |
| Database | `testdb` |
| User | `dba` |
| Password | *(empty)* |

## Learning Path

```
connect/ → crud/ → transactions/ → parameterized-queries/ → orm-basics/
```

After fundamentals, continue to:
- [quickstart/](../quickstart/) — 5-minute working API
- [templates/](../templates/) — Production-ready starters
- [performance/](../performance/) — Optimization patterns
- [pitfalls/](../pitfalls/) — Common mistakes to avoid
