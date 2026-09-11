# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **One-command dashboard demo** — `templates/dashboard/` now ships its own `docker-compose.yml` (CUBRID **11.4** + Streamlit at http://localhost:8501), and the five recipes read `DATABASE_URL` from the environment (default unchanged: `cubrid+pycubrid://dba@localhost:33000/testdb`) so the compose service can point them at the co-located container.

### Docs
- Added `SUPPORT.md` (help channels, templates, security pointer) — root-file parity with the sibling repos instead of relying on the org fallback.
- **Documentation site launched** — mkdocs-material site deployed to https://cubrid-lab.github.io/cubrid-cookbook-python/ (`index.md` catalog overview + `quickstart.md` three-path guide), matching the sibling repos' Pages setups. README's private org-board link removed (404 for signed-out readers).
- **`GETTING_STARTED.md` restructured as the judge/demo entry point** — three-path flow (pycubrid first query → ORM/templates → `uvx cubrid-mcp-server` with the four natural-language steps incl. the read-only refusal), expected-output pointers to the CI-checked goldens, and fixed stale `fundamentals/connect/`-style links that no longer matched the directory layout.

- **CUBRID server license line added; copyright notice unified (#99)** — `THIRD_PARTY_LICENSES.md` states the verified upstream licensing (server engine Apache-2.0, APIs/connectors BSD per CUBRID's `COPYING`; GPL v2+ is outdated) and that the examples are independent clients with `cubrid/cubrid` images used for CI/demo only. LICENSE/NOTICE copyright unified to `Yeongseon Choe, Gyeongjun Paik` (2025-2026), replacing the `CUBRID Labs` line.

### Docs
- **Added `THIRD_PARTY_LICENSES.md` and `NOTICE`** — pip-licenses-generated inventory of the union of template/example requirements (all permissive; no GPL), and a NOTICE declaring the examples original with no embedded third-party source. Documentation only.

- **Corrected the async recipe's `sqlalchemy-cubrid` floor from `>=1.0` to `>=1.4.2` (#94)** — `fundamentals/async/02_async_sqlalchemy.py` builds an `AsyncEngine` with the `cubrid+aiopycubrid://` URL, but that async dialect (`cubrid.aiopycubrid` entry point) only became installable from PyPI in `sqlalchemy-cubrid` 1.2.3 — the entry points were missing from the 1.2.0–1.2.1 releases and 1.2.2 was yanked; 1.2.1 only shipped the `get_pool_class()`/`create_async_engine()` fix (#116). So the recipe's `sqlalchemy-cubrid>=1.0` pin (in its `requirements.txt`, its printed "Requirements:" line, and the matching golden) advertised a version that cannot run it. Bumped all three to `>=1.4.2`, matching the floor already used by the other advanced SQLAlchemy recipes (pandas, ORM, Django, dashboard) rather than the bare 1.2.3 minimum. `SUPPORT_MATRIX.md` now carries an `[^async]` footnote documenting that the sync dialect works from 1.0 while the async recipe needs `>=1.4.2`. The global README badge stays at `>=1.0`: the sync `cubrid+pycubrid://` recipes (including all FastAPI templates, which use `create_engine`, not `create_async_engine`) genuinely run on 1.0.
- **SUPPORT_MATRIX bug fixes (#57)** — fixed the "Run all tests" commands, which chained two relative `cd`s so the second (`templates/api-service-fastapi/recipes`) resolved against `templates/flask/` and failed; each is now wrapped in a subshell. Added the previously-omitted `async-worker` (Celery) and `batch-etl` (Pandas) templates to the recipe-coverage table as manual-run entries and updated the total. (The version-badge/matrix and Python-table inconsistencies from the same issue were already resolved in #80 and #81.)
- **Reconciled the minimum `sqlalchemy-cubrid` version to `>=1.0` (#80)** — the README badge advertised `≥1.6.0` while `SUPPORT_MATRIX.md` listed `≥1.0`, and scattered `requirements.txt` files pinned stale/invalid versions (`>=2.0.0`, which does not exist; `>=0.4.1`; `>=0.3.0`). Aligned the badge and the invalid/pre-1.0 stragglers to `>=1.0` (the documented source of truth); feature-specific `>=1.4.2` pins were left unchanged.
- **README fundamentals link renamed to "Parameterized queries" (#82)** — the link targeting `fundamentals/parameterized-queries/` was labelled "Prepared statements", implying server-side prepare that pycubrid does not do; relabelled to "Parameterized queries" with a client-side note to match the recipe's own README warning.
- **SUPPORT_MATRIX Python table fixed (#81)** — added a **3.14** row and re-sorted the Python versions table into consistent descending order (3.14 → 3.9); previously 3.14 was missing and 3.13 was listed after 3.10.
- **SUPPORT_MATRIX corrected to match CI (#72)** — the matrix claimed CUBRID 11.4 was "fully supported" and "all 62 recipes pass", but CI only runs `make verify` (46 stdout goldens) on CUBRID 11.2 / Python 3.12; the Flask/FastAPI/Streamlit/Django pytest suites and CUBRID 11.4 are never exercised in CI. Reworded the server/Python/recipe tables to state exactly what CI enforces vs. what is run manually or merely expected to work, removing the unenforced green checkmarks.

### Changed
- **Templates now install `pycubrid` and `sqlalchemy-cubrid` from PyPI instead of `git+…@main`** — the `async-worker`, `batch-etl`, and `flask` templates' `requirements.txt` pinned both drivers to the `main` branch heads, so a template install could break whenever `main` moved and required a git toolchain at deploy time. They now pin `pycubrid>=1.7,<2` and `sqlalchemy-cubrid>=1.7,<2` (the current PyPI releases). The `api-service-fastapi` template's `pycubrid>=0.0.4` floor — a pre-release number predating the first public PyPI release — is raised to the same `>=1.7,<2` pin.

### CI
- **Pinned `ruff` to `0.16.4` in CI (#78)** — the lint job installed `ruff` unpinned, so formatter/linter rule changes in new ruff releases could break CI unpredictably; pinned to `0.16.4` to match the version used by `pycubrid` and `sqlalchemy-cubrid`.
- **Golden-coverage guard closes the silent-skip gap (#89)** — added `scripts/check_expected_coverage.py`, wired into `make verify` (via a new `check-coverage` target) and the `smoke-test.yml` workflow. `make verify` is golden-driven, so any `*.py` inside a directory that owns an `expected/` folder but lacks a matching `expected/<name>.expected` golden was silently never executed in CI. The guard now fails loudly on any such uncovered script (exceptions go in `scripts/verify_exclusions.txt` with a reason).
- **Smoke tests now run a CUBRID 11.2 + 11.4 job matrix** — `smoke-test.yml` previously started a single `cubrid/cubrid:11.2` container; it now runs `make verify` goldens against both 11.2 and 11.4, giving the "expected to work" claim for 11.4 in `SUPPORT_MATRIX.md` direct CI evidence. `SUPPORT_MATRIX.md` updated accordingly.

### Fixed
- **Regenerated the two LOB goldens that recorded pycubrid's pre-1.7.0 escaping bug** — `fundamentals/pycubrid/expected/06_lob.expected` and `fundamentals/lob-handling/expected/06_lob.expected` were captured while pycubrid silently negotiated the wrong `no_backslash_escapes` mode (the bug fixed loud in pycubrid 1.7.0, pycubrid#263/#293), so every newline in the round-tripped CLOB text carried a stray backslash (`64 chars` → `66 chars`). pycubrid 1.7.0 fixed the corruption, which made the nightly smoke red against these stale goldens since Sep 4. Goldens regenerated from the now-correct output against CUBRID 11.2; `make verify` passes 23/23.
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
