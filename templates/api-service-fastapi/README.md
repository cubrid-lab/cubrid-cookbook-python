# FastAPI + CUBRID API Service Template

## Overview

Production-ready starter template for building REST APIs with FastAPI, SQLAlchemy 2.0, and CUBRID 11.2.
It is intentionally lean: sync SQLAlchemy session lifecycle, clean repository pattern, and Docker-first local setup.

## Quick Start

1. Copy this template and move into the directory.
2. Create your environment file:

   ```bash
   cp .env.example .env
   ```

3. Start services:

   ```bash
   docker compose up --build
   ```

4. Open:
   - API: `http://localhost:8000`
   - Swagger UI: `http://localhost:8000/docs`
   - Health: `http://localhost:8000/health`

## Project Structure

```text
app/
├── main.py          # FastAPI app factory, lifespan, CORS
├── config.py        # pydantic-settings based configuration
├── database.py      # SQLAlchemy engine/session/base
├── models.py        # cookbook_items, cookbook_categories
├── schemas.py       # Request/response models
├── crud.py          # Repository pattern CRUD logic
└── routes/
    ├── health.py    # GET /health
    └── items.py     # Item CRUD endpoints
```

## API Endpoints

- `GET /health` → `{"status": "ok", "database": "connected"}`
- `GET /items?skip=0&limit=20` → paginated item list
- `GET /items/{item_id}` → single item
- `POST /items` → create item
- `PUT /items/{item_id}` → update item
- `DELETE /items/{item_id}` → delete item

## Configuration

Environment variables (see `.env.example`):

- `DATABASE_URL` (default `cubrid+pycubrid://dba@cubrid:33000/testdb`)
- `APP_HOST` (default `0.0.0.0`)
- `APP_PORT` (default `8000`)

Additional settings in `app/config.py`:

- `APP_NAME`
- `DEBUG`
- `CORS_ORIGINS`

## Development

- Tables are auto-created at startup via `Base.metadata.create_all()`.
- SQLAlchemy access is fully parameterized through ORM/query builder usage.
- Keep this template starter-focused: no auth, no migrations, no framework over-abstraction.
- Run locally without Docker:

  ```bash
  pip install -r requirements.txt
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

- Do not add `index=True` to primary key columns: CUBRID rejects a second index
  on columns a primary key or `UNIQUE` constraint already indexes, so
  `create_all()` fails at startup.
- Each recipe under `recipes/` ships a test suite that runs against live CUBRID
  when `CUBRID_TEST_URL` is set and falls back to in-memory SQLite otherwise.
  See the Test section of each recipe's README.
