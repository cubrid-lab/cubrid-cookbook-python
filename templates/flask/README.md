# Flask + Flask-SQLAlchemy CUBRID Recipes

This directory contains standalone Flask recipes that demonstrate progressively richer CUBRID-backed JSON API patterns with Flask-SQLAlchemy.

## Requirements

- Python 3.11+
- A recipe-specific Python virtual environment
- A live CUBRID instance when running a recipe application. The basic CRUD app defaults to `cubrid+pycubrid://dba@localhost:33000/testdb`; from the repository root, `make up` starts the supported local CUBRID service.
- CUBRID is optional for tests: the test fixtures use a temporary SQLite database unless `CUBRID_TEST_URL` is set.

## Recipe Layout

Each numbered directory is a self-contained recipe with its own README, application files, and tests:

- `01-basic-crud/`
- `02-categories/`
- `03-inventory-ledger/`
- `04-purchase-orders/`
- `05-batch-operations/`
- `06-case-triage/`
- `07-vendor-feed/`
- `08-transactional-outbox/`
- `09-rbac/`
- `10-workflow-engine/`
- `11-inventory-reservation/`

Start with `01-basic-crud` and follow the README in each recipe for its endpoints and any recipe-specific setup.

## Run a Recipe

For example, start the repository's local CUBRID service, then run the basic CRUD recipe:

```bash
# From the repository root:
make up

cd templates/flask/01-basic-crud
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The basic CRUD recipe exposes JSON Product CRUD endpoints under `/api/products`. To use another supported CUBRID instance, set `DATABASE_URL` before starting the app, for example:

```bash
DATABASE_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python run.py
```

## Test

Run a recipe's test suite from that recipe directory. For `01-basic-crud`:

```bash
cd templates/flask/01-basic-crud
pip install pytest
python -m pytest tests/ -v
```

Tests use a temporary SQLite database by default. To run them against a live CUBRID instance, set `CUBRID_TEST_URL`, consistent with the per-recipe README:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python -m pytest tests/ -v
```

## More Detail

Each numbered recipe documents its own endpoints, examples, and any additional requirements. For focused database error recipes, see the repository's `fundamentals/error-handling/` examples.
