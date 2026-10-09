# Java to Python Migration Guide

> **Zero data migration required.** CUBRID's JDBC driver and Python driver (`pycubrid`)
> use the same CAS broker protocol — your database, schema, and data stay exactly as-is.

## Why Migrate?

| Dimension | Java (JDBC) | Python (pycubrid) | Python (SQLAlchemy) |
|-----------|-------------|--------------------|--------------------|
| Connection setup | 8–12 lines | 4 lines | 3 lines |
| CRUD (full cycle) | ~60 lines | ~25 lines | ~20 lines |
| Batch insert 1K rows | ~30 lines | 3 lines (`executemany`) | 2 lines (`add_all`) |
| Transaction handling | Manual try/catch/finally | `with` context manager | Session auto-rollback |
| Error handling | Checked exceptions | Python exceptions | SQLAlchemy exceptions |
| ORM integration | JPA/Hibernate (complex) | SQLAlchemy (simple) | Built-in |

### Lines of Code Comparison

```
                         Java JDBC    pycubrid    SQLAlchemy
Connection               12           4           3
Single INSERT            8            3           2
SELECT + iterate         15           5           4
Transaction block        20           6           5
Batch INSERT (1K rows)   30           3           2
─────────────────────────────────────────────────────────
Total                    85           21          16
Reduction                —            75%         81%
```

## Performance

Our [benchmark results](../../performance/) show pycubrid performs well after recent optimizations:

- **Connection**: a query on a fresh connection took ~5.9 ms vs ~0.8 ms pooled (pycubrid 1.10.0, 2026-10-09)
- **Single INSERT + COMMIT**: ~36 ms per row (pycubrid 1.10.0, 2026-10-09)

> Per-row COMMIT ran at ~28 rows/s vs ~1,279 rows/s with a COMMIT every 500 rows (pycubrid 1.10.0). Batch your writes!
> Earlier 0.5.0 figures are kept as historical in the [benchmark results](../../performance/).

## File Overview

| File | What You'll Learn |
|------|-------------------|
| [01_connection.py](01_connection.py) | Connection patterns — JDBC `DriverManager` → pycubrid `connect()` |
| [02_crud_dbapi.py](02_crud_dbapi.py) | CRUD with raw DB-API — `PreparedStatement` → parameterized queries |
| [03_crud_orm.py](03_crud_orm.py) | CRUD with SQLAlchemy ORM — JPA Entity → Mapped class |
| [04_transaction.py](04_transaction.py) | Transaction patterns — try/catch/finally → `with` blocks |
| [05_batch_operations.py](05_batch_operations.py) | Batch operations — `addBatch/executeBatch` → `executemany` |

## Migration Checklist

- [ ] Install Python dependencies: `pip install -r requirements.txt`
- [ ] Replace JDBC connection strings with pycubrid `connect()` calls
- [ ] Replace `PreparedStatement` with parameterized `cursor.execute(sql, params)`
- [ ] Replace `ResultSet` iteration with `fetchall()` / `fetchone()` / `fetchmany()`
- [ ] Replace try/catch/finally with Python `with` blocks or try/except/finally
- [ ] Replace `addBatch/executeBatch` with `cursor.executemany()`
- [ ] Replace JPA entities with SQLAlchemy models (optional — pycubrid works fine standalone)
- [ ] Update CI/CD pipeline (Maven/Gradle → pip/Poetry)
- [ ] Run existing SQL queries unchanged — CUBRID SQL syntax is identical regardless of driver

## Key Differences to Watch

1. **Parameter markers**: JDBC uses `?` — pycubrid also uses `?` (same!)
2. **Auto-commit**: JDBC defaults to auto-commit ON — pycubrid defaults to auto-commit OFF
3. **Resource cleanup**: JDBC requires explicit `close()` in finally — Python has `with` statements
4. **Null handling**: JDBC `wasNull()` pattern — Python returns `None` naturally
5. **Type mapping**: Java types map cleanly to Python types (see table below)

### Type Mapping

| CUBRID Type | Java Type | Python Type |
|-------------|-----------|-------------|
| INT | `int` | `int` |
| BIGINT | `long` | `int` |
| DOUBLE / FLOAT | `double` | `float` |
| VARCHAR / CHAR | `String` | `str` |
| DATE | `java.sql.Date` | `datetime.date` |
| TIME | `java.sql.Time` | `datetime.time` |
| TIMESTAMP | `java.sql.Timestamp` | `datetime.datetime` |
| BLOB / CLOB | `Blob` / `Clob` | `bytes` / `str` |
| NULL | `null` + `wasNull()` | `None` |
