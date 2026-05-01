# 11 Inventory Reservation with Expiry

Standalone Flask recipe for inventory reservation with optimistic concurrency and TTL-based expiry.

Run: `python run.py`
Test: `python3 -m pytest tests/ -v`

## Endpoints

- `POST /items` create inventory item
- `GET /items/<sku>` get inventory with available quantity
- `POST /reservations` reserve quantity until `expires_at`
- `GET /reservations/<reservation_key>` get reservation state
- `POST /reservations/<reservation_key>/confirm` convert reserved -> committed
- `POST /reservations/<reservation_key>/cancel` release reserved quantity
- `POST /sweeps/expire` expire stale reservations with per-row savepoints

## Notes

- Reservation uses conditional `UPDATE ... WHERE version = ?` and stock check.
- Quantity updates use SQL expressions (`reserved_qty +/- quantity`, `committed_qty + quantity`).
- Expiry sweep isolates row failures with `db.session.begin_nested()`.
