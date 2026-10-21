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

## Upgrading a stack started from an earlier compose file

Before #413 the `cubrid` service had no fixed host name, and CUBRID records the
host name of the container that created the database. The new file recreates the
container with the host name `cubrid-api-service` but keeps its database, so the
health check fails with `-353 Failed to connect to database server` and the API
does not start. Point the database at the new host name once, from this folder:

```bash
docker compose up -d cubrid
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-api-service/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
docker compose up -d
```

If the data is disposable, run `docker compose down -v` and then
`docker compose up --build` instead, to start with a fresh database.

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
