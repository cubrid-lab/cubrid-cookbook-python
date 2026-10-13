# 08 Transactional Outbox

Invoice events with outbox lease/ack/fail/dead-letter flow recipe.

Run: `python run.py`

## Leases

`POST /api/outbox/lease` claims pending messages with a conditional UPDATE and
increments `attempts`. `POST /api/outbox/<id>/ack` and `/fail` settle a message
only while the caller still holds the lease it was given: their UPDATE checks
`leased_by`, `leased_until > now`, `status = 'pending'` and the `attempts` value
the endpoint read, in the `WHERE` clause, and returns 409 unless exactly one row
changed. A lease that expired and was taken again (by another processor, or by
the same one with a new attempt) between the read and the write is therefore not
overwritten.

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
