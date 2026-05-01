# Known Issues & Limitations

This document lists known CUBRID server-level limitations that affect Python cookbook examples.
Workarounds are provided at the Python driver level where possible.

## 1. CARDINALITY() Function Not Working

**Status**: Server bug (CUBRID 11.x)  
**Tracker**: https://github.com/cubrid-lab/.github/issues/3

CUBRID documents `CARDINALITY()` for collection types but the server returns
"Function CARDINALITY is undefined" at runtime.

### Workaround

Use a subquery with `TABLE()` unnest:

```sql
-- Instead of: SELECT CARDINALITY(tags) FROM articles
SELECT (SELECT COUNT(*) FROM TABLE(a.tags) AS u) AS tag_count
FROM articles a
```

In SQLAlchemy, `func.cardinality()` will raise a clear `CompileError` with this guidance
(sqlalchemy-cubrid >= 0.3.0).

In pycubrid >= 1.3.3, the error message includes a hint with the workaround.

---

## 2. Reserved Word Column Names

**Status**: Server limitation (by design)  
**Tracker**: https://github.com/cubrid-lab/.github/issues/5

CUBRID has many reserved words (`day`, `count`, `value`, `data`, `date`, etc.)
that cannot be used as unquoted identifiers.

### Workaround

**Option A (recommended)**: Avoid reserved words in column names.
```python
# Bad:  Column('day', Date)
# Good: Column('metric_day', Date)
```

**Option B**: Use double-quotes (SQLAlchemy does this automatically):
```python
# SQLAlchemy auto-quotes reserved words in DDL
class Metric(Base):
    day = mapped_column(Date)  # generates: "day" DATE ✅
```

**Option C**: Manual quoting in raw SQL:
```sql
CREATE TABLE t ("day" DATE, "count" INTEGER);
```

In pycubrid >= 1.3.3, syntax errors for reserved words include a helpful hint
identifying the problematic identifier.

---

## 3. DDL Auto-Commits

**Status**: Server behavior (by design)

All DDL statements (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, etc.) implicitly
commit the current transaction. This means:

- Migrations are not transactional
- You cannot roll back DDL changes
- Mix of DDL and DML in one transaction may produce unexpected commits

### Workaround

Separate DDL operations from DML transactions. Run schema changes independently.

---

## 4. No RETURNING Clause

**Status**: Server limitation

CUBRID does not support `INSERT ... RETURNING` or `UPDATE ... RETURNING`.

### Workaround

```python
# Use LAST_INSERT_ID() or cursor.lastrowid (via SQLAlchemy)
result = session.execute(insert(User).values(name="Alice"))
new_id = result.inserted_primary_key[0]
```

---

## Upstream Fix Tracking

These issues require CUBRID server-level fixes and are tracked for future resolution:

| Issue | Description | Upstream Status |
|-------|-------------|-----------------|
| [.github#3](https://github.com/cubrid-lab/.github/issues/3) | CARDINALITY() runtime error | Open |
| [.github#5](https://github.com/cubrid-lab/.github/issues/5) | Reserved word error messages | Open |

Until server-level fixes land, workarounds are provided in:
- **sqlalchemy-cubrid**: Auto-quoting, CompileError for CARDINALITY
- **pycubrid**: Error message hints
