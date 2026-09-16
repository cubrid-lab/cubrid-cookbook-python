# 07 Document Publishing

Standalone FastAPI recipe extracted from the monolith.

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Test

```bash
pip install pytest pytest-asyncio httpx
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database by default. Set `CUBRID_TEST_URL` to run
them against a live CUBRID instance:

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python -m pytest tests/ -v
```
