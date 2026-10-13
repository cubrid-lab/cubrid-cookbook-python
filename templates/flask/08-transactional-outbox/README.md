# 08 Transactional Outbox

Invoice events with outbox lease/ack/fail/dead-letter flow recipe.

Run: `python run.py`

## Leases

`POST /api/outbox/lease` claims pending messages with a conditional UPDATE,
increments `attempts`, and returns each claimed message. A lease is identified by
the `processor_id` that took it and the `attempts` value returned for it.

`POST /api/outbox/<id>/ack` and `/fail` need both in the request body:

```json
{"processor_id": "worker-1", "lease_attempt": 1}
```

`/fail` also takes an optional `"error"` string. `lease_attempt` is the
`attempts` value from the `/lease` response. It is required: a missing
`lease_attempt` returns 409 (the request does not show which lease it holds), and
a value that is not an integer returns 400. The settlement is one UPDATE whose `WHERE` clause
checks `leased_by`, `leased_until > now`, `status = 'pending'` and
`attempts = lease_attempt`, and it returns 409 unless exactly one row changed.
So a request for a lease that expired and was taken again (by another processor,
or by the same `processor_id` with a new attempt number) cannot settle the newer
lease, whether the re-lease happened before the request was read or between its
read and its write.

Before #339 the request had no `lease_attempt`, and a stale request sent after
the same `processor_id` leased the message again could settle the newer lease.
Callers of this recipe must now send `lease_attempt`.

## Test

```bash
pip install -r requirements.txt pytest httpx
python3 -m pytest tests/ -v
```

Tests use a temporary SQLite database by default. Set `CUBRID_TEST_URL` to run
them against a live CUBRID instance:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python3 -m pytest tests/ -v
```
