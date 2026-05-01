# Support Matrix

Tested combinations of CUBRID server, Python version, and driver/framework.

## CUBRID Server Versions

| CUBRID | Status | Notes |
|--------|--------|-------|
| **11.4** | ✅ Fully supported | All 55 recipes pass |
| **11.2** | ✅ Fully supported | Primary development/test target |
| 11.0 | ⚠️ Untested | Should work (same CAS protocol) |
| 10.2 | ⚠️ Untested | Should work (same CAS protocol) |

## Python Versions

| Python | Status |
|--------|--------|
| **3.10** | ✅ Tested (CI default) |
| **3.11** | ✅ Compatible |
| **3.12** | ✅ Compatible |
| **3.13** | ✅ Compatible |
| 3.9 | ❌ Not supported (`from __future__ import annotations` patterns) |

## Driver & Framework Versions

| Component | Version | Status |
|-----------|---------|--------|
| pycubrid | ≥ 1.3.2 | ✅ Required |
| sqlalchemy-cubrid | ≥ 0.3.0 | ✅ Required for SQLAlchemy recipes |
| SQLAlchemy | 2.0–2.1 | ✅ |
| Flask | ≥ 3.0 | ✅ |
| Flask-SQLAlchemy | ≥ 3.1 | ✅ |
| FastAPI | ≥ 0.100 | ✅ |
| Pandas | ≥ 2.0 | ✅ |
| Streamlit | ≥ 1.30 | ✅ |
| Django | ≥ 5.0 | ✅ (minimal recipe) |

## Recipe Test Results

All recipes tested against CUBRID 11.2 and 11.4:

| Category | Recipes | CUBRID 11.2 | CUBRID 11.4 |
|----------|---------|-------------|-------------|
| pycubrid fundamentals | 14 | ✅ All pass | ✅ All pass |
| SQLAlchemy fundamentals | 6 | ✅ All pass | ✅ All pass |
| Pandas fundamentals | 6 | ✅ All pass | ✅ All pass |
| Flask templates | 11 | ✅ All pass | ✅ All pass |
| FastAPI templates | 12 | ✅ All pass | ✅ All pass |
| Streamlit templates | 5 | ✅ All pass | ✅ All pass |
| Django template | 1 | ✅ Pass | ✅ Pass |
| **Total** | **55** | **✅** | **✅** |

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
image: cubrid/cubrid:11.4   # also fully supported
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
