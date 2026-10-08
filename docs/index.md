# cubrid-cookbook-python

Runnable Python examples and production-shaped application templates for CUBRID — from a five-minute first query to natural-language database access, everything installs from PyPI.

- **100+ runnable recipes** across pycubrid, SQLAlchemy, pandas, Alembic, JSON, isolation levels, migration, and the application templates (exact counts in the [support matrix](support-matrix.md#recipe-coverage))
- **Every golden-backed recipe is CI-verified** — `make verify` compares exact stdout against `expected/*.expected` files on a **CUBRID 11.2 + 11.4 job matrix** for every `main` push, nightly and release verification; pull requests check the examples they touch on 11.4
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
| Flask / FastAPI templates | 11 + 12 | pytest suites (CI on `main` + nightly, CUBRID 11.2 + 11.4) |
| Streamlit / Django templates | 5 + 1 | Streamlit: isolated CUBRID pytest suite; Django: HTTP + SQLAlchemy bridge pytest (both PR CI 11.4 when touched and non-PR 11.2 + 11.4) |
| Celery / batch-ETL templates | 1 + 5 | Celery database tasks: live pytest (PR CI 11.4 when touched; `main` + nightly 11.2 + 11.4), broker/worker manual; ETL goldens in `expected/` |
| Async · Alembic · JSON · isolation | 4 | `make verify` goldens (CI) |
| Migration, performance, pitfalls | topic guides | docs |

Numbers and status per [SUPPORT_MATRIX.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/SUPPORT_MATRIX.md).

Smoke tests keep the selected published driver versions fixed through all
dependency installs and verify versions and package-index origin before reporting
the packages exercised. Upstream release dispatches install the exact requested
version, wait within a bounded publication budget, and fail if it remains
unavailable. A final summary records request, actual versions/origins, verification
commit, server version and result even when validation fails. See the
[release smoke dependency contract](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/CONTRIBUTING.md#release-smoke-dependencies).

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
