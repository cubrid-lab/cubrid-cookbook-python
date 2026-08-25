# Support Matrix

Tested combinations of CUBRID server, Python version, and driver/framework.

> **What "tested" means here**: CI runs `make verify` on **CUBRID 11.2 / Python
> 3.12**, comparing stdout against the **46 recipes that ship goldens**
> (`expected/*.expected`). The Flask, FastAPI, Streamlit, and Django recipes are
> covered by pytest suites that are **run manually** (see [How to Test](#how-to-test-against-a-specific-version)),
> not in CI. CUBRID 11.4 has no CI job.

## CUBRID Server Versions

| CUBRID | Status | Notes |
|--------|--------|-------|
| **11.2** | ✅ CI-verified | Primary CI target — 46 example outputs checked by `make verify` |
| **11.4** | ⚠️ Expected to work | Same CAS protocol as 11.2; **not exercised in CI** |
| 11.0 | ⚠️ Untested | Should work (same CAS protocol) |
| 10.2 | ⚠️ Untested | Should work (same CAS protocol) |
> **Scope note**: CI exercises only CUBRID **11.2** with Python **3.12**. Older
> versions (10.2, 11.0) and newer 11.4 share the same CAS protocol and should
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
| sqlalchemy-cubrid | ≥ 1.0 | ✅ Required for SQLAlchemy recipes |
| SQLAlchemy | 2.0–2.2 | ✅ |
| Flask | ≥ 3.0 | ✅ |
| Flask-SQLAlchemy | ≥ 3.1 | ✅ |
| FastAPI | ≥ 0.100 | ✅ |
| Pandas | ≥ 2.0 | ✅ |
| Streamlit | ≥ 1.30 | ✅ |
| Django | ≥ 5.0 | ✅ (minimal recipe) |

## Recipe Coverage

The cookbook ships **62 recipes**. Verification is split:

- **46 recipes** carry stdout goldens (`expected/*.expected`) and are checked by
  `make verify` in CI on **CUBRID 11.2 / Python 3.12** (fundamentals, migration,
  quickstart, and the golden-backed templates).
- The **Flask, FastAPI, Streamlit, and Django** recipes are covered by pytest
  suites that are **run manually** (see [How to Test](#how-to-test-against-a-specific-version)),
  not in CI.
- **CUBRID 11.4** has no CI job; it shares the CAS protocol with 11.2 and is
  expected to work but is not exercised automatically.

| Category | Recipes | Verified by |
|----------|---------|-------------|
| pycubrid fundamentals | 16 | `make verify` (CI, 11.2) |
| SQLAlchemy fundamentals | 7 | `make verify` (CI, 11.2) |
| Pandas fundamentals | 6 | `make verify` (CI, 11.2) |
| Flask templates | 11 | pytest (manual) |
| FastAPI templates | 12 | pytest (manual) |
| Streamlit templates | 5 | manual run |
| Django template | 1 | manual run |
| Async + Alembic + JSON + Isolation | 4 | `make verify` (CI, 11.2) |
| **Total** | **62** | 46 CI-verified on 11.2; rest run manually |

## Known Limitations by Version

| Issue | CUBRID 11.2 | CUBRID 11.4 | Workaround |
|-------|-------------|-------------|------------|
| CARDINALITY() broken | ❌ | ❌ | Use COUNT(*) + TABLE() unnest |
| Reserved word errors | ⚠️ Cryptic error | ⚠️ Cryptic error | Use double-quotes or rename |
| No RETURNING clause | ❌ | ❌ | Use LAST_INSERT_ID() |
| DDL auto-commits | By design | By design | Separate DDL from DML |

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for details and workarounds.

## Docker Images

```yaml
# docker-compose.yml — change tag to test different versions
image: cubrid/cubrid:11.2   # default
image: cubrid/cubrid:11.4   # expected to work; not exercised in CI
```

## How to Test Against a Specific Version

```bash
# Edit docker-compose.yml to use desired CUBRID version, then:
docker compose down -v
docker compose up -d
sleep 60  # wait for DB initialization

# Run all tests
cd templates/flask && for d in */tests; do python3 -m pytest "$d" -q; done
cd templates/api-service-fastapi/recipes && for d in */tests; do python3 -m pytest "$d" -q; done

# Run fundamentals
for f in fundamentals/pycubrid/*.py; do python3 "$f"; done
for f in fundamentals/sqlalchemy/*.py; do python3 "$f"; done
for f in fundamentals/pandas/*.py; do python3 "$f"; done
```
