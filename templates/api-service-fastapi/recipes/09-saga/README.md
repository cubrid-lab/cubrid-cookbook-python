# FastAPI Saga (Compensating Transactions)

Standalone FastAPI recipe implementing a Saga with compensating transactions for order execution.

## Files

- `main.py` - FastAPI app
- `database.py` - SQLAlchemy engine/session/base
- `models.py` - order, inventory, payment, and saga step models
- `schemas.py` - request/response models
- `routes.py` - all endpoints and saga flow
- `tests/test_main.py` - recipe test suite

## Install

```bash
cd /data/GitHub/cubrid-cookbook/python/fastapi/09-saga
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

## Test

```bash
python -m pytest tests/ -v
```
