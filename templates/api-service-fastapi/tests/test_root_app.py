"""Startup smoke test for the root FastAPI template app (``templates/api-service-fastapi/app``).

Imports the real ``app.main`` module, runs its lifespan (``create_all``) and calls
``/health`` through ``TestClient``. The app builds its engine from ``DATABASE_URL`` at
import time, so the test points it at a throwaway SQLite file and needs no CUBRID.
An import error, a missing dependency (for example ``pydantic-settings``) or a startup
failure in the app fails this test. SQLite cannot catch CUBRID-specific SQL differences;
the recipe suites cover those against a live server.

Run it in its own process with the template's own requirements installed:

    pip install pytest httpx -r templates/api-service-fastapi/requirements.txt
    python -m pytest templates/api-service-fastapi/tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
if str(TEMPLATE_ROOT) not in sys.path:
    sys.path.insert(0, str(TEMPLATE_ROOT))

_DB_DIR = tempfile.TemporaryDirectory()
# Settings are cached on first use, so set the environment before importing the app.
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(_DB_DIR.name) / 'root_app.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_app_starts_and_reports_healthy() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200, response.text
    assert response.json().get("status") == "ok"
