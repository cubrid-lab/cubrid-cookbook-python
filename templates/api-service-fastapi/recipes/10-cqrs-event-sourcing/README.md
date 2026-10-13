# FastAPI CQRS + Event Sourcing

Standalone FastAPI recipe showing CQRS with an event store, read model projection, optimistic concurrency, and snapshot-based rehydration.

## Files

- `main.py` - FastAPI app bootstrap
- `database.py` - SQLAlchemy engine/session/base
- `models.py` - event store, snapshots, and account read model tables
- `schemas.py` - request/response contracts
- `routes.py` - command/query endpoints and projection logic
- `tests/test_main.py` - end-to-end tests
- `tests/conftest.py` - test database fixture (live CUBRID or in-memory SQLite)

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

## Rebuilding the read model

Commands project each new event into the read model and skip a state the read
model has already reached (`sequence_no <= last_sequence_no`), so replaying an
event twice does nothing. A rebuild is different: it replays the stream and
overwrites the read model row with the result even when the sequence number is
not newer, so it repairs a read model that drifted from the events.
`{"from_scratch": 1}` replays every event from the first; `{"from_scratch": 0}`
starts from the latest snapshot and replays the events after it. Both still use
the read model's version guard, and the UPDATE also requires
`last_sequence_no <= :replayed_tail`: if a command commits a newer event after the
rebuild replayed the stream, the rebuild returns 409 instead of rewinding the read
model to the older state.

## Test

```bash
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database by default. Set `CUBRID_TEST_URL` to run
them against a live CUBRID instance:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python -m pytest tests/ -v
```
