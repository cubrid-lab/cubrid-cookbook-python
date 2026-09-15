# Support Matrix

Tested combinations of CUBRID server, Python version, and driver/framework.

> **What "tested" means here**: CI runs `make verify` on **CUBRID 11.2 and 11.4 / Python
> 3.12** (job matrix), comparing stdout against the **65 recipes that ship goldens**
> (`expected/*.expected`). The Flask, FastAPI, Streamlit, and Django recipes are
> covered by pytest suites that are **run manually** (see [How to Test](#how-to-test-against-a-specific-version)),
> not in CI.

## CUBRID Server Versions

| CUBRID | Status | Notes |
|--------|--------|-------|
| **11.2** | ✅ CI-verified | Primary CI target — 65 example outputs checked by `make verify` |
| **11.4** | ✅ CI-verified | Same CAS protocol as 11.2; runs in the smoke-test job matrix (`make verify` goldens) |
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
| SQLAlchemy | 2.0–2.2 | ✅ |
| Flask | ≥ 3.0 | ✅ |
| Flask-SQLAlchemy | ≥ 3.1 | ✅ |
| FastAPI | ≥ 0.100 | ✅ |
| Pandas | ≥ 2.0 | ✅ |
| Streamlit | ≥ 1.30 | ✅ |
| Django | ≥ 5.0 | ✅ (minimal recipe) |

[^async]: The sync SQLAlchemy dialect (`cubrid+pycubrid://`) works from `sqlalchemy-cubrid` 1.0. The async dialect (`cubrid+aiopycubrid://`, used by `fundamentals/async/02_async_sqlalchemy.py`) first became installable from PyPI in 1.2.3 (its entry points were missing from the 1.2.0–1.2.1 releases and 1.2.2 was yanked; 1.2.1 only shipped the `get_pool_class()`/`create_async_engine()` fix), and this cookbook pins it to `≥ 1.4.2` to match the floor of the other advanced SQLAlchemy recipes (pandas, ORM, Django, dashboard).

## Recipe Coverage

The cookbook ships **95 recipes**. Verification is split:

- **65 recipes** carry stdout goldens (`expected/*.expected`) and are checked by
  `make verify` in CI on **CUBRID 11.2 / Python 3.12** (fundamentals, migration,
  quickstart, and the golden-backed templates).
- The **Flask, FastAPI, Streamlit, and Django** recipes are covered by pytest
  suites that are **run manually** (see [How to Test](#how-to-test-against-a-specific-version)),
  not in CI. The FastAPI suites run against live CUBRID when `CUBRID_TEST_URL` is
  set and fall back to in-memory SQLite otherwise.
- **CUBRID 11.4** runs in the same CI smoke matrix as 11.2 (its `make verify` goldens
  are checked on both versions).
- The **Flask** pytest suites run against live CUBRID when `CUBRID_TEST_URL` is set
  and fall back to temporary SQLite databases otherwise.

| Category | Recipes | Verified by |
|----------|---------|-------------|
| pycubrid fundamentals | 16 | `make verify` (CI, 11.2) |
| SQLAlchemy fundamentals | 7 | `make verify` (CI, 11.2) |
| Pandas fundamentals | 6 | `make verify` (CI, 11.2) |
| Flask templates | 11 | pytest (manual) |
| FastAPI templates | 12 | pytest (manual; live CUBRID via `CUBRID_TEST_URL`) |
| Streamlit templates | 5 | manual run |
| Django template | 1 | manual run |
| Celery async-worker template | 1 | manual run |
| Pandas batch-etl template | 5 | manual run (goldens in `expected/`) |
| Async + Alembic + JSON + Isolation | 4 | `make verify` (CI, 11.2) |
| **Total** | **95** | 65 CI-verified on 11.2; rest run manually |

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

# Run fundamentals
for f in fundamentals/pycubrid/*.py; do python3 "$f"; done
for f in fundamentals/sqlalchemy/*.py; do python3 "$f"; done
for f in fundamentals/pandas/*.py; do python3 "$f"; done
```

The pytest suites create and drop their tables in whichever database
`CUBRID_TEST_URL` points at, and a few table names are shared between suites
(`inventory_items` in FastAPI recipe 09 and Flask recipe 11, `cookbook_products`
in Flask recipes 01 and 07). Run the suites one after another against a shared
instance, as the loops above do, or give concurrent runs separate databases.
