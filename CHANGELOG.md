# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Docs
- **SUPPORT_MATRIX bug fixes (#57)** — fixed the "Run all tests" commands, which chained two relative `cd`s so the second (`templates/api-service-fastapi/recipes`) resolved against `templates/flask/` and failed; each is now wrapped in a subshell. Added the previously-omitted `async-worker` (Celery) and `batch-etl` (Pandas) templates to the recipe-coverage table as manual-run entries and updated the total. (The version-badge/matrix and Python-table inconsistencies from the same issue were already resolved in #80 and #81.)
- **Reconciled the minimum `sqlalchemy-cubrid` version to `>=1.0` (#80)** — the README badge advertised `≥1.6.0` while `SUPPORT_MATRIX.md` listed `≥1.0`, and scattered `requirements.txt` files pinned stale/invalid versions (`>=2.0.0`, which does not exist; `>=0.4.1`; `>=0.3.0`). Aligned the badge and the invalid/pre-1.0 stragglers to `>=1.0` (the documented source of truth); feature-specific `>=1.4.2` pins were left unchanged.
- **README fundamentals link renamed to "Parameterized queries" (#82)** — the link targeting `fundamentals/parameterized-queries/` was labelled "Prepared statements", implying server-side prepare that pycubrid does not do; relabelled to "Parameterized queries" with a client-side note to match the recipe's own README warning.
- **SUPPORT_MATRIX Python table fixed (#81)** — added a **3.14** row and re-sorted the Python versions table into consistent descending order (3.14 → 3.9); previously 3.14 was missing and 3.13 was listed after 3.10.
- **SUPPORT_MATRIX corrected to match CI (#72)** — the matrix claimed CUBRID 11.4 was "fully supported" and "all 62 recipes pass", but CI only runs `make verify` (46 stdout goldens) on CUBRID 11.2 / Python 3.12; the Flask/FastAPI/Streamlit/Django pytest suites and CUBRID 11.4 are never exercised in CI. Reworded the server/Python/recipe tables to state exactly what CI enforces vs. what is run manually or merely expected to work, removing the unenforced green checkmarks.

### CI
- **Pinned `ruff` to `0.16.4` in CI (#78)** — the lint job installed `ruff` unpinned, so formatter/linter rule changes in new ruff releases could break CI unpredictably; pinned to `0.16.4` to match the version used by `pycubrid` and `sqlalchemy-cubrid`.
- **Golden-coverage guard closes the silent-skip gap (#89)** — added `scripts/check_expected_coverage.py`, wired into `make verify` (via a new `check-coverage` target) and the `smoke-test.yml` workflow. `make verify` is golden-driven, so any `*.py` inside a directory that owns an `expected/` folder but lacks a matching `expected/<name>.expected` golden was silently never executed in CI. The guard now fails loudly on any such uncovered script (exceptions go in `scripts/verify_exclusions.txt` with a reason).

### Fixed
- **De-duplicated the parameterized-queries recipe golden (#79)** — `fundamentals/parameterized-queries/04_parameterized.py` was a byte-for-byte copy of the canonical `fundamentals/pycubrid/04_prepared.py`, and both shipped `expected/` goldens, so `make verify` counted the same recipe twice. The topic entry is now a thin redirect to the canonical recipe (its `expected/` golden removed and the folder allowlisted in `scripts/docs-sync-allowlist.txt`), dropping the CI golden count from 46 to 45 while keeping topic-based discovery intact.
- **Fixed 3 broken examples the missing-golden gap was hiding (#89)** — backfilled `expected/` goldens for 11 previously-unverified scripts and, in doing so, uncovered and fixed three broken examples: `fundamentals/error-handling/03_query_timeout.py` (a server-side `lock_timeout` system parameter did not bound the blocked client on CUBRID 11.2, so the demo hung forever — rewritten to use a client-side `pycubrid.connect(..., read_timeout=…)`); `fundamentals/pycubrid/12_pool_retry_worker.py` (hung at cleanup because a pooled connection still held a lock when `DROP TABLE` ran — the `finally` now closes the pool before dropping); and `fundamentals/pycubrid/16_batch_error_handling.py` (crashed on a duplicate-key retry that assumed post-failure statements were skipped — rewritten to teach the real CUBRID all-or-nothing `rollback()` semantics, and a module-level `print` that scrambled output order was moved into `main()`).
- **Added datetime-microsecond and bulk-insert timing rules to `scripts/normalize_output.sh`** — `{{DATE}} HH:MM:SS.ffffff` now normalizes to `{{DATETIME}}` and the `execute(insert, rows):`/`add_all:` perf-summary lines normalize their seconds to `{{TIME}}s`, so the merge/serial/bulk-insert examples produce reproducible goldens. Covered by new `scripts/test_normalize_output.sh` cases.

### Added
- CUBRID-distinctive SQL feature recipes (6 new pycubrid scripts):
  - `fundamentals/pycubrid/17_window_functions.py` — ROW_NUMBER/RANK/DENSE_RANK, LAG, running SUM over partitions (with deterministic tie-breakers)
  - `fundamentals/pycubrid/18_recursive_cte.py` — `WITH RECURSIVE` number series and hierarchy path building (contrast with 08 CONNECT BY)
  - `fundamentals/pycubrid/19_pagination.py` — `LIMIT`/`OFFSET` vs CUBRID-idiomatic `FOR ORDERBY_NUM() BETWEEN`, plus the `ROWNUM` caveat
  - `fundamentals/pycubrid/20_timezone_datetime.py` — `DATETIMETZ`/`DATETIMELTZ` native reads and `SET TIME ZONE`; `TIMESTAMPTZ` rendered via server-side `TO_CHAR` to sidestep [pycubrid#289](https://github.com/cubrid-lab/pycubrid/issues/289)
  - `fundamentals/pycubrid/21_enum_type.py` — ENUM declaration-order sorting, `col + 0` ordinal, out-of-set rejection
  - `fundamentals/pycubrid/22_date_formatting.py` — `TO_CHAR`/`TO_DATE` date and number formatting with visible fixed-width padding
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
