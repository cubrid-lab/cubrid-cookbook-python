# FastAPI CQRS + Event Sourcing

Standalone FastAPI recipe showing CQRS with an event store, read model projection, optimistic concurrency, and snapshot-based rehydration.

## Files

- `main.py` - FastAPI app bootstrap
- `database.py` - SQLAlchemy engine/session/base
- `models.py` - event store, snapshots, and account read model tables
- `schemas.py` - request/response contracts
- `routes.py` - command/query endpoints and projection logic
- `tests/test_main.py` - end-to-end tests with in-memory SQLite

## Run

```bash
cd /data/GitHub/cubrid-cookbook/python/fastapi/10-cqrs-event-sourcing
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

- `POST /accounts` - append `AccountOpened` and project read model
- `POST /accounts/{account_id}/deposit` - append `MoneyDeposited` with optimistic concurrency
- `POST /accounts/{account_id}/withdraw` - rehydrate from snapshot + tail, reject overdraft, append `MoneyWithdrawn`
- `GET /accounts/{account_id}` - query read model
- `GET /accounts/{account_id}/events` - list aggregate event stream ordered by sequence
- `POST /accounts/{account_id}/snapshot` - create or replace aggregate snapshot
- `POST /accounts/{account_id}/rebuild` - rebuild read model from snapshot+tail or full stream

## Test

```bash
python -m pytest tests/ -v
```
