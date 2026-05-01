# Django + CUBRID (SQLAlchemy Bridge)

Django does not have a native CUBRID backend. This example shows how to use SQLAlchemy as a bridge while keeping Django for request handling.

Connection URL: `cubrid+pycubrid://dba@localhost:33000/testdb`

## Minimal structure

```text
python/django/
├── manage.py
├── settings.py
├── app/
│   ├── __init__.py
│   ├── db.py
│   ├── urls.py
│   └── views.py
├── requirements.txt
└── README.md
```

## Install and run

```bash
pip install -r requirements.txt
python3 manage.py runserver
```

## Routes (JSON only)

- `GET /health` checks CUBRID with `SELECT 1`
- `GET /items` lists rows from `cookbook_items`
- `POST /items` creates one row

Example create payload:

```json
{
  "title": "first item",
  "is_active": true
}
```

`is_active` is saved as integer `1` or `0`.

## Table creation hook

`app/views.py` uses lazy initialization with `_ensure_tables_initialized()` to create `cookbook_items` on first request.

## Quick check

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/items -H "content-type: application/json" -d '{"title":"hello"}'
curl -s http://127.0.0.1:8000/items
```
