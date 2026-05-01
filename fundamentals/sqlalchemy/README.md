# SQLAlchemy Recipes (Standalone Scripts)

Six copy-paste friendly SQLAlchemy 2.0 scripts for CUBRID.
Each recipe is a single `.py` file you can run directly with `python3`.

Connection used by all recipes:

`cubrid+pycubrid://dba@localhost:33000/testdb`

## Prerequisites

- Python 3.10+
- CUBRID running on `localhost:33000` (`testdb`, user `dba`)

From repository root:

```bash
make up
```

## Install

```bash
pip install -r requirements.txt
```

## Recipes

1. `01_connect_and_session.py`
   - Engine creation, Session usage, `SELECT 1`, connection metadata, clean shutdown
2. `02_orm_crud.py`
   - ORM model with `DeclarativeBase` and `mapped_column`, full CRUD lifecycle
3. `03_relationships.py`
   - Department/Employee relationship, lazy/eager loading, child-first deletion
4. `04_bulk_insert.py`
   - Bulk insert via `session.execute(insert(), rows)` vs `add_all`, timing comparison
5. `05_cubrid_upsert.py`
   - CUBRID `ON DUPLICATE KEY UPDATE` and `REPLACE INTO` via `sqlalchemy_cubrid.dml`
6. `06_reflection.py`
   - Runtime schema discovery with `inspect()` and Inspector API

## Run

```bash
python3 01_connect_and_session.py
python3 02_orm_crud.py
python3 03_relationships.py
python3 04_bulk_insert.py
python3 05_cubrid_upsert.py
python3 06_reflection.py
```

## Notes

- Every script creates its own `cookbook_` tables, seeds data, demonstrates the feature, and drops tables in `finally`.
- Boolean-like values are stored as `Integer` (`0`/`1`).
- Money values are stored as integer cents.
- No DB-level cascade is used; related deletes are handled in application code.
