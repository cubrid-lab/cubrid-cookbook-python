# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Docs
- **Reconciled the minimum `sqlalchemy-cubrid` version to `>=1.0` (#80)** — the README badge advertised `≥1.6.0` while `SUPPORT_MATRIX.md` listed `≥1.0`, and scattered `requirements.txt` files pinned stale/invalid versions (`>=2.0.0`, which does not exist; `>=0.4.1`; `>=0.3.0`). Aligned the badge and the invalid/pre-1.0 stragglers to `>=1.0` (the documented source of truth); feature-specific `>=1.4.2` pins were left unchanged.
- **README fundamentals link renamed to "Parameterized queries" (#82)** — the link targeting `fundamentals/parameterized-queries/` was labelled "Prepared statements", implying server-side prepare that pycubrid does not do; relabelled to "Parameterized queries" with a client-side note to match the recipe's own README warning.
- **SUPPORT_MATRIX Python table fixed (#81)** — added a **3.14** row and re-sorted the Python versions table into consistent descending order (3.14 → 3.9); previously 3.14 was missing and 3.13 was listed after 3.10.
- **SUPPORT_MATRIX corrected to match CI (#72)** — the matrix claimed CUBRID 11.4 was "fully supported" and "all 62 recipes pass", but CI only runs `make verify` (46 stdout goldens) on CUBRID 11.2 / Python 3.12; the Flask/FastAPI/Streamlit/Django pytest suites and CUBRID 11.4 are never exercised in CI. Reworded the server/Python/recipe tables to state exactly what CI enforces vs. what is run manually or merely expected to work, removing the unenforced green checkmarks.

### CI
- **Pinned `ruff` to `0.16.4` in CI (#78)** — the lint job installed `ruff` unpinned, so formatter/linter rule changes in new ruff releases could break CI unpredictably; pinned to `0.16.4` to match the version used by `pycubrid` and `sqlalchemy-cubrid`.

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
