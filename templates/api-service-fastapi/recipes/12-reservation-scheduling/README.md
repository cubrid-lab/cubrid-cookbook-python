# FastAPI Recipe: Reservation Scheduling

Standalone FastAPI recipe implementing resource reservation with overlap checks, optimistic serialization, and FIFO waitlist promotion.

## Features

- Resource creation with unique `resource_key`
- Reservation creation with SQL overlap detection: `existing.start_at < end_at AND existing.end_at > start_at`
- Resource-level optimistic serialization through version bump to reduce booking races
- Reservation cancellation with optimistic lock and FIFO waitlist promotion
- Waitlist create/list endpoints for waiting and promoted entries

## Files

- `main.py`
- `database.py`
- `models.py`
- `schemas.py`
- `routes.py`
- `requirements.txt`
- `tests/test_main.py`

## Setup

```bash
cd /data/GitHub/cubrid-cookbook/python/fastapi/12-reservation-scheduling
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

## Endpoints

- `POST /resources`
  - Body: `{resource_key, name, slot_minutes}`
  - `409` duplicate key, `400/422` invalid input.
- `POST /reservations`
  - Body: `{reservation_key, resource_key, requester_id, start_at, end_at}`
  - `404` resource not found, `409` overlap/race/duplicate key, `400` invalid interval.
- `GET /reservations/{reservation_key}`
  - `404` if not found.
- `GET /resources/{resource_key}/reservations?from_at=...&to_at=...`
  - Returns reservations overlapping the requested window.
- `POST /reservations/{reservation_key}/cancel`
  - Cancels reservation and promotes first matching waitlist entry if available.
- `POST /resources/{resource_key}/waitlist`
  - Body: `{requester_id, desired_start_at, desired_end_at}`
  - `404` resource not found, `400` invalid interval.
- `GET /resources/{resource_key}/waitlist`
  - Lists `waiting`/`promoted` entries in FIFO order.

Datetime fields use naive UTC ISO strings.

## Test

```bash
pytest tests/test_main.py -q
```
