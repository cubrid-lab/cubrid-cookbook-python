# ⚡ 5-Minute Quickstart: FastAPI + CUBRID

## 1) Prerequisites
Install Docker Desktop (or Docker Engine + Docker Compose).

## 2) Start the database and API

Run both services in Docker:

```bash
docker compose up -d --build
```

Alternatively, run the API on your host with Python 3.11+:

```bash
docker compose up -d --wait cubrid
pip install -r requirements.txt
uvicorn app:app --reload
```

This starts only the database container so port 8000 remains available for
Uvicorn. The host-run API defaults to `localhost`; set `CUBRID_HOST` for a remote
database. Compose sets `CUBRID_HOST=cubrid` when running the API in its container.

## 3) Verify API is running
```bash
curl localhost:8000/items
```

You should get a JSON array response (for example, `[]` on first run).

The app creates its table in FastAPI's lifespan startup hook. Blocking database
work runs in a thread, including the synchronous request handlers. Each database
operation commits on success, rolls back on failure, and closes its cursor and
connection. For connection reuse in a production API, see the
[SQLAlchemy starter](../../templates/api-service-fastapi/README.md).

## Test without a database

```bash
pip install -r requirements.txt pytest httpx
python -m pytest tests -q
```

The tests replace the DB-API connection and cover host configuration, startup,
CRUD responses, and resource cleanup after database failures.

## What's Next?
- Production-ready starter: `../../templates/api-service-fastapi/`
- Core database patterns: `../../fundamentals/`
