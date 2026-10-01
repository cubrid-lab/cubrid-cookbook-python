# Support Matrix

Tested combinations of CUBRID server, Python version, and driver/framework.

> **What "tested" means here**: CI runs `make verify` on **CUBRID 11.2 and 11.4 / Python
> 3.12** (job matrix), comparing stdout against every recipe that ships a golden
> (`expected/*.expected`; counts in [Recipe Coverage](#recipe-coverage)); a pull request
> that touches only examples checks just those examples. On pushes to `main`, the nightly schedule and manual
> runs, the same matrix job runs the **Flask and FastAPI pytest suites** on its
> original CUBRID container, then stops it and runs the **Streamlit dashboard
> pytest suite** on a separate, disposable CUBRID container of the same
> version. Every pull request runs representative Flask/FastAPI and dashboard
> suites in separate live CUBRID 11.4 jobs (`ci.yml`). The
> **Django** recipe is still **run manually** (see [How to
> Test](#how-to-test-against-a-specific-version)).

## CUBRID Server Versions

| CUBRID | Status | Notes |
|--------|--------|-------|
| **11.2** | ✅ CI-verified | Primary CI target — every golden-backed example output checked by `make verify` (example-only pull requests check just the changed examples) |
| **11.4** | ✅ CI-verified | Same CAS protocol as 11.2; runs in the smoke-test job matrix (`make verify` goldens, plus isolated Flask/FastAPI and dashboard pytest suites on non-PR runs) |
| 11.0 | ⚠️ Untested | Should work (same CAS protocol) |
| 10.2 | ⚠️ Untested | Should work (same CAS protocol) |
> **Scope note**: CI exercises CUBRID **11.2 and 11.4** (smoke-test job matrix) with
> Python **3.12**. Older versions (10.2, 11.0) share the same CAS protocol and should
> work but are **not exercised in CI**. The drivers (`pycubrid`,
> `sqlalchemy-cubrid`) themselves run the full 10.2–11.4 matrix in their own
> repositories.

## Python Versions

| Python | Status |
|--------|--------|
| **3.14** | ⚠️ Expected to work (not in CI) |
| **3.13** | ⚠️ Expected to work (not in CI) |
| **3.12** | ✅ Tested (CI default) |
| **3.11** | ⚠️ Expected to work (not in CI) |
| **3.10** | ⚠️ Minimum; expected to work (not in CI) |
| 3.9 | ❌ Not supported (`from __future__ import annotations` patterns) |

## Driver & Framework Versions

| Component | Version | Status |
|-----------|---------|--------|
| pycubrid | ≥ 1.6.1 | ✅ Required |
| sqlalchemy-cubrid | ≥ 1.0 | ✅ Required for SQLAlchemy recipes (≥ 1.4.2 for the async `cubrid+aiopycubrid://` recipe [^async]) |
| SQLAlchemy | 2.0–2.2 | ✅ Async recipes install the `sqlalchemy[asyncio]` extra for the required greenlet runtime |
| Flask | ≥ 3.0 | ✅ |
| Flask-SQLAlchemy | ≥ 3.1 | ✅ |
| FastAPI | ≥ 0.100 | ✅ |
| Pandas | ≥ 2.0 | ✅ |
| Streamlit | ≥ 1.30 | ✅ |
| Django | ≥ 5.0 | ✅ (minimal recipe) |

[^async]: The sync SQLAlchemy dialect (`cubrid+pycubrid://`) works from `sqlalchemy-cubrid` 1.0. The async dialect (`cubrid+aiopycubrid://`, used by `fundamentals/async/02_async_sqlalchemy.py`) first became installable from PyPI in 1.2.3 (its entry points were missing from the 1.2.0–1.2.1 releases and 1.2.2 was yanked; 1.2.1 only shipped the `get_pool_class()`/`create_async_engine()` fix), and this cookbook pins it to `≥ 1.4.2` to match the floor of the other advanced SQLAlchemy recipes (pandas, ORM, Django, dashboard).

The `fundamentals/connect` and `fundamentals/orm-basics` requirements use
`pycubrid>=1.7,<2`; ORM basics also uses `sqlalchemy-cubrid>=1.7,<2`.
`fundamentals/pycubrid` requires `pycubrid>=1.8,<2`: its
`16_batch_error_handling` and `20_timezone_datetime` goldens assume the
`errno`-carrying batch errors (#390) and the CAS session kept across
`commit()` (#468/#472) that first shipped in pycubrid 1.8.0. These
example-specific floors do not change the minimum versions for other recipes
in the table above.

The full example apps under `templates/` (`flask`, `api-service-fastapi`,
`ai-agent`, `async-worker`, `batch-etl`, and each of their standalone
per-recipe `requirements.txt`) pin `pycubrid>=1.7,<2` — the `flask` family
(including its recipes) also pins `sqlalchemy-cubrid>=1.7,<2` — instead of the
bare global floor above. This is a deliberate, separate policy for installable
apps (they used to install both drivers from `git+…@main`; see "Templates now
install `pycubrid` and `sqlalchemy-cubrid` from PyPI" in the changelog) and is
not itself a correctness floor for any single recipe; `scripts/check_dependency_floors.py`
treats it as a documented per-family exception rather than drift.

The smoke workflow selects published drivers, constrains all later dependency
installs to those exact versions, and verifies their versions and package-index
origin after installation. Its **Tested upstream versions** summary describes the
drivers actually exercised, rather than versions recorded before example installs.
Conflicting requirements or VCS/local replacements fail the job. Release dispatches
also install the exact requested package version, with bounded PyPI publication
retry, and verify it after all dependency installs. The final summary includes
requested/installed versions, origin, verification commit, actual server version
when available, and result even on failed runs. See
[Release smoke dependencies](CONTRIBUTING.md#release-smoke-dependencies).

## Recipe Coverage

The table below is the source of truth for recipe counts;
`scripts/check_support_matrix_counts.py` (run by `make check-docs`) fails
when a row no longer matches the repository. Verification is split:

- **Golden-backed recipes** carry stdout goldens (`expected/*.expected`) and are
  checked by `make verify` in CI on **CUBRID 11.2 and 11.4 / Python 3.12**
  (fundamentals, migration, the SQLAlchemy quickstart, the batch-etl template, and
  the reserved-word DDL check behind `pitfalls/`).
- The **Flask and FastAPI** recipes are covered by pytest suites that the smoke
  job runs against its live CUBRID container on **11.2 and 11.4** for every push
  to `main`, nightly, and on manual runs (pull requests skip them to stay fast).
  Each suite's `conftest.py` reads `CUBRID_TEST_URL`; without it the suites fall
  back to SQLite for local runs.
- The **Streamlit** recipes are covered by `templates/dashboard/tests/test_dashboard.py`
  (`AppTest`-based: seeded table viewer rows, non-empty KPI metrics, and a
  filter that changes the rendered row count). On pushes to `main`, nightly,
  and manual runs, the smoke job runs it on a **separate disposable CUBRID
  container** for each matrix version (**11.2 and 11.4**) after the shared
  Flask/FastAPI container is stopped. On every pull request, a separate
  required `ci.yml` job runs it against its own CUBRID **11.4** container.
  It falls back to a shared SQLite file when `CUBRID_TEST_URL` is unset.
  Its `conftest.py` drops its own `cookbook_sales` and `cookbook_products`
  in FK-safe order, but isolation—not test ordering or cross-recipe deletion—
  protects the Flask suite's `cookbook_products` (#142). The **Django**
  recipe is still **run manually** (see [How to Test](#how-to-test-against-a-specific-version)).
- The **FastAPI quickstart** has an offline pytest suite in PR CI for host and
  Compose configuration, startup, HTTP responses, and database failure cleanup.
  It uses mocked DB-API connections rather than a live server.
- The **five AI agent scripts** run via `tests/test_ai_agent.py` against live
  **11.2 and 11.4** on every smoke-test trigger, including pull requests.
  Each script runs with a 60-second limit; the suite drops its own example
  tables before and after each case and runs twice to verify repeatability.
  `tests/test_ai_agent_offline.py` checks ID handling, MCP errors and cleanup.
- **CUBRID 11.4** runs in the same CI smoke matrix as 11.2 (its `make verify` goldens
  are checked on both versions).

| Category | Recipes | Verified by |
|----------|---------|-------------|
| pycubrid fundamentals | 22 | `make verify` (CI, 11.2 + 11.4) |
| SQLAlchemy fundamentals | 7 | `make verify` (CI, 11.2 + 11.4) |
| SQLAlchemy ORM basics | 6 | `make verify` (CI, 11.2 + 11.4) |
| Pandas fundamentals | 6 | `make verify` (CI, 11.2 + 11.4) |
| Connect, CRUD, errors, transactions, LOB | 8 | `make verify` (CI, 11.2 + 11.4) |
| Async + Alembic + JSON + Isolation | 5 | `make verify` (CI, 11.2 + 11.4) |
| Java-to-Python migration | 5 | `make verify` (CI, 11.2 + 11.4) |
| SQLAlchemy quickstart | 1 | `make verify` (CI, 11.2 + 11.4) |
| Pandas batch-etl template | 5 | `make verify` (CI, 11.2 + 11.4) |
| Pitfalls: reserved-word DDL | 1 | `make verify` (CI, 11.2 + 11.4) |
| Flask templates | 11 | pytest (CI on `main` + nightly, 11.2 + 11.4) |
| FastAPI templates | 12 | pytest (CI on `main` + nightly, 11.2 + 11.4) |
| FastAPI quickstart | 1 | offline pytest (PR CI, mocked DB-API) |
| AI agent template | 5 | pytest (smoke CI incl. PRs, 11.2 + 11.4) |
| Streamlit templates | 5 | pytest (CI on `main` + nightly, 11.2 + 11.4; also PR CI on 11.4) |
| Django template | 1 | manual run |
| Celery async-worker template | 1 | manual run |
| **Total** | **102** | 66 golden-backed via `make verify` on 11.2 + 11.4; Flask, FastAPI and Streamlit pytest suites in CI on `main` + nightly (plus representative PR CI); AI agent suite on every smoke run; Django and Celery run manually |

## Known Limitations by Version

| Issue | CUBRID 11.2 | CUBRID 11.4 | Workaround |
|-------|-------------|-------------|------------|
| CARDINALITY() broken | ❌ | ❌ | Use COUNT(*) + TABLE() unnest |
| Reserved word errors | ⚠️ Cryptic error | ⚠️ Cryptic error | Use double-quotes or rename |
| No RETURNING clause | ❌ | ❌ | Use LAST_INSERT_ID() |
| DDL auto-commits | By design | By design | Separate DDL from DML |
| Duplicate index on indexed columns | ❌ | ❌ | Drop `index=True` on primary key / unique columns |

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for details and workarounds.

## Docker Images

```yaml
# docker-compose.yml — change tag to test different versions
image: cubrid/cubrid:11.2   # default
image: cubrid/cubrid:11.4   # also exercised in CI (smoke-test job matrix)
```

## How to Test Against a Specific Version

```bash
# Edit docker-compose.yml to use desired CUBRID version, then:
docker compose down -v
docker compose up -d
sleep 60  # wait for DB initialization

# Run all tests
# Flask recipe tests use live CUBRID when CUBRID_TEST_URL is set and fall back
# to temporary SQLite databases when it is not
pip install flask flask-sqlalchemy pycubrid sqlalchemy-cubrid httpx pytest
export CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb"
( cd templates/flask && for d in */tests; do python3 -m pytest "$d" -q; done )

# FastAPI recipe tests use live CUBRID when CUBRID_TEST_URL is set and fall back
# to in-memory SQLite when it is not
pip install fastapi sqlalchemy pycubrid sqlalchemy-cubrid "email-validator>=2" httpx pytest pytest-asyncio
export CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb"
( cd templates/api-service-fastapi/recipes && for d in */tests; do python3 -m pytest "$d" -q; done )

# Streamlit dashboard recipe tests (AppTest) use live CUBRID when
# CUBRID_TEST_URL is set and fall back to a shared SQLite file when it is not
pip install -r templates/dashboard/requirements.txt pytest
export CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb"
python3 -m pytest templates/dashboard/tests -q

# Run fundamentals
for f in fundamentals/pycubrid/*.py; do python3 "$f"; done
for f in fundamentals/sqlalchemy/*.py; do python3 "$f"; done
for f in fundamentals/pandas/*.py; do python3 "$f"; done
```

The pytest suites create and drop their tables in whichever database
`CUBRID_TEST_URL` points at. Some suites share table names (`inventory_items`
in FastAPI recipe 09 and Flask recipe 11; `cookbook_products` in Flask recipes
01 and 07 and the dashboard). Run the Flask/FastAPI suites sequentially, and
give the dashboard suite a **different database/container**: its
`cookbook_sales` foreign key references `cookbook_products`, so leftover
dashboard tables in a shared database can block Flask teardown even if the
suites normally run in order. CI uses separate CUBRID containers; the
dashboard fixture only deletes tables in its own database.
