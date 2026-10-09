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
(sqlalchemy-cubrid >= 1.0).

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

## 3. DDL Is Transactional Only While Autocommit Is Off

**Status**: Server behavior (by design)

CUBRID DDL (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `CREATE INDEX`, ...)
runs inside the current transaction, like DML. It does **not** implicitly
commit. What decides when it commits is the client's autocommit mode:

- **Autocommit off** (pycubrid's default, and what sqlalchemy-cubrid sets on
  every connection): DDL stays uncommitted until `COMMIT`, and `ROLLBACK`
  undoes it, together with any DML in the same transaction. This is why
  sqlalchemy-cubrid's Alembic implementation reports `transactional_ddl = True`
  (since 1.8.0): by default a failed `alembic upgrade` rolls back the whole run,
  including the `alembic_version` update (see the `transaction_per_migration`
  caveat below).
- **Autocommit on** (`conn.autocommit = True`, SQLAlchemy
  `isolation_level="AUTOCOMMIT"`, csql's default auto-commit mode,
  or a client such as JDBC that defaults to autocommit): every statement,
  DDL or DML, commits on its own, so there is nothing left to roll back.

Verified live on CUBRID 11.2 and 11.4 (this cookbook) and on 10.2 and 11.4
(sqlalchemy-cubrid's transactional-DDL tests).

```python
conn = pycubrid.connect(...)  # autocommit is off by default
cur = conn.cursor()
cur.execute("CREATE TABLE t_tmp (id INT)")
conn.rollback()  # t_tmp no longer exists
```

### Caveats

- **Schema locks are held until commit.** Uncommitted DDL keeps its schema lock
  on the table, so other sessions that touch the table wait until the
  transaction ends (CUBRID's default `lock_timeout` is unlimited). Commit DDL
  promptly; for long Alembic migrations set `transaction_per_migration=True` in
  `context.configure()` so each revision commits and releases its locks.
- **Offline (`alembic upgrade --sql`) scripts** must be run with
  `csql --no-auto-commit --no-single-line`; in csql's default modes every
  statement commits and a failing statement does not stop the script.

See sqlalchemy-cubrid's
[Alembic guide](https://github.com/cubrid-lab/sqlalchemy-cubrid/blob/main/docs/ALEMBIC.md#transactional-ddl)
for details.

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

## 5. Duplicate Index on Already-Indexed Columns

**Status**: Server behavior (CUBRID 11.2 and 11.4)

CUBRID rejects a second index over exactly the same columns as an existing
primary key, `UNIQUE` constraint, or index:

```text
Index "pk_cookbook_tasks_id" already defined for class "dba.cookbook_tasks".
```

SQLite accepts the redundant index silently, so a model can pass SQLite-backed
tests and still fail `Base.metadata.create_all()` on CUBRID. In SQLAlchemy the
usual trigger is `index=True` on a primary key column, or on a column that a
`UniqueConstraint` already covers.

### Workaround

Do not add `index=True` to columns that a primary key or `UNIQUE` constraint
already indexes:

```python
# Bad:  fails on CUBRID with "Index ... already defined"
id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

# Good: the primary key already provides the index
id: Mapped[int] = mapped_column(Integer, primary_key=True)
```

`unique=True, index=True` on the same column is fine (SQLAlchemy emits a single
`CREATE UNIQUE INDEX`), and so is `index=True` on a foreign key column.

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
