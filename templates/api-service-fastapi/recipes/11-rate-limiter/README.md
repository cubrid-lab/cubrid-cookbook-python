# FastAPI Recipe: Rate Limiter (Sliding Window)

Standalone FastAPI recipe that implements per-client rate limiting using a sliding-window counter with optimistic locking.

## Features

- Client policy management (`limit_per_window`, `window_seconds`, `burst_allowance`)
- Sliding-window weighted count: `current_count + int(previous_count * overlap_fraction)`
- SQL expression increment on consume (`current_count = current_count + :cost`)
- Optimistic version checks for policy update and reset
- Standard rate-limit headers on successful consume

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
cd /data/GitHub/cubrid-cookbook/python/fastapi/11-rate-limiter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

## Endpoints

- `POST /clients`
  - Creates client and zeroed rate window.
  - `409` on duplicate `client_key`, `400/422` on invalid input.
- `PUT /clients/{client_key}/policy`
  - Updates policy with `expected_version`.
  - `404` not found, `409` stale version.
- `POST /clients/{client_key}/consume`
  - Applies sliding-window check and consumes quota.
  - `429` with `Retry-After` when exceeded.
  - Success headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- `GET /clients/{client_key}/quota`
  - Returns current and previous counters plus computed remaining.
- `POST /clients/{client_key}/reset`
  - Clears counters with optimistic lock (`expected_version`).
- `GET /clients/{client_key}`
  - Returns client policy info.

## Test

```bash
pytest tests/test_main.py -q
```

The tests avoid `sleep()` and patch `datetime.utcnow` through a recipe-local `utcnow` helper.
