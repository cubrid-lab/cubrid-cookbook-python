# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Docs
- **SUPPORT_MATRIX corrected to match CI (#72)** — the matrix claimed CUBRID 11.4 was "fully supported" and "all 62 recipes pass", but CI only runs `make verify` (46 stdout goldens) on CUBRID 11.2 / Python 3.12; the Flask/FastAPI/Streamlit/Django pytest suites and CUBRID 11.4 are never exercised in CI. Reworded the server/Python/recipe tables to state exactly what CI enforces vs. what is run manually or merely expected to work, removing the unenforced green checkmarks.

### Added
- v1.6.x feature recipes (8 new scripts):
  - `fundamentals/async/` — pycubrid.aio + SQLAlchemy async engine
  - `fundamentals/alembic/` — programmatic Alembic migration with CubridImpl
  - `fundamentals/json/` — native JSON columns, JSON_EXTRACT/UNQUOTE patterns
  - `fundamentals/isolation-levels/` — 6 CUBRID levels + dirty-read demo
  - `fundamentals/sqlalchemy/07_collection_types.py` — SET/MULTISET/SEQUENCE ORM
  - `fundamentals/pycubrid/15_cursor_memory_bound.py` — fetch_size + tracemalloc
  - `fundamentals/pycubrid/16_batch_error_handling.py` — executemany_batch error paths

### Previous Releases
- Python examples: FastAPI, Django, Flask, SQLAlchemy, pycubrid, Pandas, Celery, Streamlit
- llms.txt for AI agent discoverability
- PRD with Example-first Design Philosophy

### Changed
- Refactored to Python-only repository (removed planned Go and Node.js examples)

### Fixed
- Python lint errors and code formatting across all examples
- All examples verified against live CUBRID instance
- `fundamentals/sqlalchemy/07_collection_types.py` — SET/MULTISET/SEQUENCE collection columns now render correct single-quoted SQL literals (with quote escaping) instead of malformed inline SQL, and the example is verified against a golden `expected/07_collection_types.expected` output (Closes #56)
