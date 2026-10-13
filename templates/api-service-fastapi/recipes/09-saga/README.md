# FastAPI Saga (Compensating Transactions)

Standalone FastAPI recipe implementing a Saga with compensating transactions for order execution.

## Files

- `main.py` - FastAPI app
- `database.py` - SQLAlchemy engine/session/base
- `models.py` - order, inventory, payment, and saga step models
- `schemas.py` - request/response models
- `routes.py` - all endpoints and saga flow
- `tests/test_main.py` - recipe test suite
- `tests/conftest.py` - test database fixture (live CUBRID or in-memory SQLite)

## Install

```bash
cd templates/api-service-fastapi/recipes/09-saga   # from the repository root
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

Default database URL:

`cubrid+pycubrid://dba@localhost:33000/testdb`

## Endpoints

- `POST /inventory-items`
- `POST /payment-accounts`
- `POST /orders`
- `POST /orders/{order_key}/execute`
- `GET /orders/{order_key}`
- `GET /orders/{order_key}/steps`
- `POST /orders/{order_key}/recover`

## curl examples

Create inventory:

```bash
curl -X POST "http://127.0.0.1:8000/inventory-items" \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU-1","available_qty":10}'
```

Create payment account:

```bash
curl -X POST "http://127.0.0.1:8000/payment-accounts" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"C1","available_cents":5000}'
```

Create order:

```bash
curl -X POST "http://127.0.0.1:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{"order_key":"O-1","client_id":"C1","sku":"SKU-1","quantity":3,"total_cents":1200}'
```

Execute saga:

```bash
curl -X POST "http://127.0.0.1:8000/orders/O-1/execute"
```

Get order:

```bash
curl -X GET "http://127.0.0.1:8000/orders/O-1"
```

Get step history:

```bash
curl -X GET "http://127.0.0.1:8000/orders/O-1/steps"
```

Recover an order stuck in `processing`:

```bash
curl -X POST "http://127.0.0.1:8000/orders/O-1/recover" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds":300}'
```

## Recovering a stuck order

`POST /orders/{order_key}/execute` commits each step's effect (the stock
reservation, the payment hold) in the same transaction that marks the step
`done`. If the process dies part way, the order stays `processing`.

`POST /orders/{order_key}/recover` puts such an order back to `pending`, but only
after it has been `processing` for longer than `timeout_seconds` (default 300); a
younger order returns 409. The reset is a conditional UPDATE on the order's
version and state. The age is measured from the order's last update, and the step
commits do not touch the order, so a run that is still active after
`timeout_seconds` can be reset. Pick a timeout well above the longest run.

Calling `execute` again then resumes the saga: steps already marked `done` are
skipped, not repeated, so each step takes effect exactly once. If a later step
fails, the skipped steps are compensated like any other completed step.

## Test

```bash
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database by default. Set `CUBRID_TEST_URL` to run
them against a live CUBRID instance:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python -m pytest tests/ -v
```
