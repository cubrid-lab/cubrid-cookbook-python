# ⚡ 5-Minute Quickstart: SQLAlchemy + CUBRID

## 1) Prerequisites
Install Docker Desktop (or Docker Engine + Docker Compose) and Python 3.11+.

## 2) Start everything
```bash
docker compose up -d --wait
```

`--wait` returns once the CUBRID health check passes, so the database
`testdb` is ready before the next step.

## 3) Verify quickstart is running
```bash
pip install -r requirements.txt
python app.py
```

You should see successful Core and ORM CRUD output. The app drops its
`cookbook_core_items` and `cookbook_orm_items` tables and disposes of its engine
before it exits, so it can be run again.

## 4) Clean up
```bash
docker compose down
```

## What's Next?
- Production-ready starter: `../../templates/batch-etl/`
- Core database patterns: `../../fundamentals/`
