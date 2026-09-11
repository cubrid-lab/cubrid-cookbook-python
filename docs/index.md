# cubrid-cookbook-python

Runnable Python examples and production-shaped application templates for CUBRID — from a five-minute first query to natural-language database access, everything installs from PyPI.

- **68 runnable examples** across pycubrid, SQLAlchemy, pandas, Alembic, JSON, isolation levels, and migration
- **45 of them are CI-verified goldens** — `make verify` compares exact stdout against `expected/*.expected` files on a **CUBRID 11.2 + 11.4 job matrix**
- **6 application templates**: FastAPI service, Flask app, Django app, Streamlit dashboard, Celery async worker, pandas batch ETL — the dashboard is a one-command `docker compose up` demo

## The three paths

| Path | Installs | Start |
|------|----------|-------|
| Driver — first query in 5 minutes | `pip install pycubrid` | [Quick Start](quickstart.md) |
| ORM & application templates | `pip install sqlalchemy-cubrid` | [Quick Start](quickstart.md#2-orm-and-application-templates-sqlalchemy-cubrid) |
| Natural language over the database | `uvx cubrid-mcp-server` | [Quick Start](quickstart.md#3-natural-language-over-the-database-cubrid-mcp-server) |

## What's inside

| Area | Examples | Verified by |
|------|----------|-------------|
| pycubrid fundamentals | 16 | `make verify` goldens (CI, CUBRID 11.2 + 11.4) |
| SQLAlchemy fundamentals | 7 | `make verify` goldens (CI) |
| pandas fundamentals | 6 | `make verify` goldens (CI) |
| Flask / FastAPI templates | 11 + 12 | pytest suites (manual runs) |
| Streamlit / Django templates | 5 + 1 | manual runs (dashboard ships a compose demo) |
| Celery / batch-ETL templates | 1 + 5 | manual runs (ETL goldens in `expected/`) |
| Async · Alembic · JSON · isolation | 4 | `make verify` goldens (CI) |
| Migration, performance, pitfalls | topic guides | docs |

Numbers and status per [SUPPORT_MATRIX.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/SUPPORT_MATRIX.md).

## Try the one-command dashboard

```bash
cd templates/dashboard
docker compose up -d   # CUBRID 11.4 + Streamlit at http://localhost:8501
```

## Ecosystem

- [pycubrid](https://github.com/cubrid-lab/pycubrid) — pure-Python DB-API 2.0 driver (sync + asyncio)
- [sqlalchemy-cubrid](https://github.com/cubrid-lab/sqlalchemy-cubrid) — SQLAlchemy 2.0–2.2 dialect
- [cubrid-mcp-server](https://github.com/cubrid-lab/cubrid-mcp-server) — MCP server for LLM clients

MIT — see [LICENSE](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/LICENSE).
