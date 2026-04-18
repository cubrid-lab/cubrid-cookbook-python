# PRD: cubrid-cookbook-python — Use-Case-Centric Python Examples for CUBRID

## 1. Overview

**Project**: cubrid-cookbook-python
**Status**: Active (continuously updated)
**Repository**: [github.com/cubrid-labs/cubrid-cookbook-python](https://github.com/cubrid-labs/cubrid-cookbook-python)
**License**: MIT

### 1.1 Problem Statement

CUBRID is a production-grade relational database widely used in Korean government and
enterprise systems. Despite having modern Python drivers and ORM dialects, the ecosystem
lacks the one thing that drives adoption in 2026:

**Runnable examples organized by what developers actually want to do.**

When developers evaluate a database, they don't read API docs first — they look for
working code they can copy-paste and run in under 60 seconds. If they can't find examples,
they move on to PostgreSQL or MySQL.

AI coding assistants (Claude Code, OpenCode, Cursor, Copilot, Devin) make this even
more critical — they recommend libraries based on the examples they can find in
documentation and repositories. No examples = no recommendation = no adoption.

### 1.2 What Was Built

A use-case-centric Python cookbook organized by developer intent:

- **Quickstart** — Working CUBRID + FastAPI app in 5 minutes
- **Migration guide** — Side-by-side Java JDBC → Python (pycubrid + SQLAlchemy)
- **Production templates** — FastAPI REST API, Celery worker, Pandas ETL, Streamlit dashboard
- **Performance patterns** — Benchmark-backed optimization (linked to cubrid-benchmark data)
- **Pitfalls** — 7 common anti-patterns with CUBRID-specific fixes
- **Fundamentals** — Step-by-step reference for every core operation

### 1.3 Success Criteria

| Criterion | Target | Status |
|---|---|---|
| 5-minute quickstart works end-to-end | Yes | Done |
| Java migration guide with side-by-side code | Yes | Done |
| Production FastAPI template with Docker | Yes | Done |
| Benchmark-backed performance patterns | Yes | Done |
| All examples verified against CUBRID 11.2 | Yes | In progress |
| Examples use `cookbook_` table prefix | Yes | Done |

---

## 2. Architecture

### 2.1 Project Structure

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

### 2.2 Shared Infrastructure

All examples connect to the same CUBRID instance:

| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `33000` |
| Database | `testdb` |
| User | `dba` |
| Password | *(empty)* |

Started via `docker compose up -d` using the shared `docker-compose.yml`.

---

## 3. Content Map

### 3.1 Organized by Developer Intent

| "I want to..." | Section | Key Files |
|---|---|---|
| Get started quickly | `quickstart/5min-fastapi/` | app.py, docker-compose.yml |
| Migrate from Java | `migration/java-to-python/` | 5 side-by-side comparison files |
| Build a production API | `templates/api-service-fastapi/` | Full app structure |
| Run background tasks | `templates/async-worker/` | Celery + CUBRID |
| Analyze data | `templates/batch-etl/` | Pandas pipeline |
| Build a dashboard | `templates/dashboard/` | Streamlit app |
| Optimize performance | `performance/` | 3 benchmark-backed patterns |
| Avoid common mistakes | `pitfalls/` | 7 anti-patterns |
| Learn fundamentals | `fundamentals/` | 7 core operation categories |

### 3.2 Fundamentals Progression

Every fundamentals topic follows numbered files with progressive complexity:

1. `01_connect` — Verify connectivity, run simple query
2. `02_crud` — Full create/read/update/delete cycle
3. `03_transactions` — Commit/rollback behavior
4. `04_prepared` — Prepared statements
5. `05_error_handling` — Exception types
6. `06_lob` — BLOB/CLOB operations
7. ORM basics — SQLAlchemy engine, core, ORM, relationships, DML extensions

---

## 4. Quality Requirements

### 4.1 Example Acceptance Criteria

Every example must:

- [ ] Run successfully against CUBRID 11.2 via Docker
- [ ] Use `cookbook_` table prefix to avoid conflicts
- [ ] Include all dependencies in `requirements.txt`
- [ ] Have a README.md with setup and run instructions
- [ ] Be independently runnable (not dependent on other examples)
- [ ] Use proper error handling (no empty catch blocks)
- [ ] Use parameterized queries (no SQL string interpolation)
- [ ] Use `from __future__ import annotations`
- [ ] Be written in English

### 4.2 Convention Rules

| Rule | Why |
|---|---|
| Table names start with `cookbook_` | Prevents conflicts with existing CUBRID tables |
| `value` → `val` in column names | `value` is a CUBRID reserved word |
| `count` → `cnt` in column names | `count` is a CUBRID reserved word |
| `data` → `file_data` in column names | `data` is a CUBRID reserved word |

---

## 5. Related Ecosystem

| Layer | Project |
|---|---|
| **DB Driver** | [pycubrid](https://github.com/cubrid-labs/pycubrid) |
| **ORM Dialect** | [sqlalchemy-cubrid](https://github.com/cubrid-labs/sqlalchemy-cubrid) |
| **Benchmarks** | [cubrid-benchmark](https://github.com/cubrid-labs/cubrid-benchmark) |
| **Database** | [CUBRID](https://www.cubrid.org/) |

---

## 6. Roadmap

### Planned Additions

| Item | Section | Priority |
|---|---|---|
| Alembic migration example | `fundamentals/` or `templates/` | Medium |
| async/await patterns with asyncio | `performance/` | Medium |
| Docker Compose multi-service template | `templates/` | Low |
| GitHub Codespaces / Devcontainer | Root | Low |
| Additional migration guides (PHP, C#) | `migration/` | Low |

---

## 7. Design Philosophy

### Use-Case-Centric Organization

This cookbook is organized by **what developers want to do**, not by framework or library.
Instead of `python/fastapi/`, `python/sqlalchemy/`, etc., we have:

- `quickstart/` — "I want to get started"
- `migration/` — "I want to switch from Java"
- `templates/` — "I want to build something real"
- `performance/` — "I want to make it fast"
- `pitfalls/` — "I want to avoid mistakes"
- `fundamentals/` — "I want to learn the basics"

This structure mirrors how developers actually think, not how libraries are organized.

### Example-first Design

> Because the ecosystem is still small, the project provides extensive examples
> and cookbook-style documentation to lower the adoption barrier.

Projects that succeeded partly through example-heavy documentation:

| Project | What They Did |
|---|---|
| **FastAPI** | Every endpoint documented with runnable examples |
| **LangChain** | Cookbook-first approach drove explosive adoption |
| **SQLAlchemy** | Extensive ORM cookbook and tutorial |
| **Pandas** | "10 Minutes to pandas" lowered entry barrier |

The cubrid-cookbook-python follows the same philosophy: **examples are not supplementary — they are the primary documentation.**

---

*Last updated: March 2026 · cubrid-cookbook-python*
