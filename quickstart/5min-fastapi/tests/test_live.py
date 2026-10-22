"""Live checks of the quickstart API against a real CUBRID (#420; ``make verify-quickstart``).

Each test drives ``app.py`` through FastAPI's ``TestClient`` and then reads the
database through a separate pycubrid connection, so a passing run proves both
the HTTP response and the stored row.

Set ``CUBRID_TEST_URL`` (for example
``cubrid+pycubrid://dba@localhost:33000/testdb``) to run them. Without it they
skip, so the offline lane stays green. With ``CUBRID_LIVE_GATE=1`` a missing URL
fails instead of skipping, and a configured but unreachable database always
fails. Tests write only rows whose ``val`` starts with their own random marker
and delete exactly those rows afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import socket
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit
import uuid

from fastapi.testclient import TestClient
import pycubrid
import pytest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
TABLE = "cookbook_quickstart_items"


@pytest.fixture(scope="module")
def target() -> dict[str, Any]:
    url = os.environ.get("CUBRID_TEST_URL")
    if not url:
        if os.environ.get("CUBRID_LIVE_GATE") == "1":
            pytest.fail("CUBRID_LIVE_GATE=1 requires CUBRID_TEST_URL", pytrace=False)
        pytest.skip("CUBRID_TEST_URL is not set; live quickstart tests skipped")
    parts = urlsplit(url)
    database = parts.path.lstrip("/")
    # app.py always connects to port 33000 and database testdb; only the host varies.
    if parts.scheme != "cubrid+pycubrid" or (parts.port or 33000) != 33000:
        pytest.fail("CUBRID_TEST_URL must be cubrid+pycubrid://...:33000/testdb", pytrace=False)
    if database != "testdb":
        pytest.fail("the quickstart app connects to database testdb only", pytrace=False)
    if (parts.username or "dba") != "dba" or parts.password:
        pytest.fail("the quickstart app connects as dba with no password", pytrace=False)
    settings = {
        "host": parts.hostname or "localhost",
        "port": 33000,
        "database": database,
        "user": parts.username or "dba",
        "password": parts.password or "",
    }
    # A configured but unavailable database must fail, never turn into a skip.
    # The bounded connect keeps an unroutable host from hanging the gate.
    try:
        with closing(pycubrid.connect(**settings, connect_timeout=10)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT 1 FROM db_root")
                assert cursor.fetchone()[0] == 1
    except Exception as exc:
        pytest.fail(f"CUBRID_TEST_URL is set but CUBRID is unreachable: {exc}", pytrace=False)
    return settings


def query(target: dict[str, Any], sql: str, params: tuple[Any, ...] = ()) -> list[tuple]:
    """Run one statement in a separate session, independent of the app's connections."""
    with closing(pycubrid.connect(**target)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall() if cursor.description else []
        conn.commit()
        return rows


@pytest.fixture
def app_module(target: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("CUBRID_HOST", target["host"])
    spec = importlib.util.spec_from_file_location("quickstart_live_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(app_module: ModuleType) -> Iterator[TestClient]:
    # Entering the client runs the lifespan hook, which creates the table.
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def marker(target: dict[str, Any]) -> Iterator[str]:
    value = f"live-qs-{uuid.uuid4().hex}"
    try:
        yield value
    finally:
        query(target, f"DELETE FROM {TABLE} WHERE val LIKE ?", (value + "%",))


def rows_with(target: dict[str, Any], marker: str) -> list[tuple]:
    return query(target, f"SELECT id, val FROM {TABLE} WHERE val LIKE ?", (marker + "%",))


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_startup_table_exists_and_health_is_ok(target, client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    tables = query(target, "SELECT class_name FROM db_class WHERE class_name = ?", (TABLE,))
    assert tables == [(TABLE,)]


def test_created_item_is_persisted_and_read_back(target, client, marker):
    created = client.post("/items", json={"val": marker})

    assert created.status_code == 200
    item = created.json()
    assert item["val"] == marker
    assert isinstance(item["id"], int)
    # The row is visible to a different session, so the API committed it.
    assert rows_with(target, marker) == [(item["id"], marker)]

    by_id = client.get(f"/items/{item['id']}")
    assert by_id.status_code == 200
    assert by_id.json() == item

    listed = client.get("/items")
    assert listed.status_code == 200
    assert item in listed.json()


def test_missing_item_returns_404(target, client):
    (highest,) = query(target, f"SELECT COALESCE(MAX(id), 0) FROM {TABLE}")[0]

    response = client.get(f"/items/{highest + 1_000_000}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.parametrize("shape", ["wrong-field", "list", "object"])
def test_invalid_payload_returns_422_and_writes_nothing(target, client, marker, shape):
    payload = {
        "wrong-field": {"value": marker},
        "list": {"val": [marker]},
        "object": {"val": {"text": marker}},
    }[shape]

    response = client.post("/items", json=payload)

    assert response.status_code == 422
    assert query(target, f"SELECT id FROM {TABLE} WHERE val LIKE ?", (f"%{marker}%",)) == []


def test_rejected_insert_returns_500_and_writes_no_row(target, client, marker):
    # val is VARCHAR(255): CUBRID rejects the longer value and the app rolls back.
    response = client.post("/items", json={"val": marker + "x" * 300})

    assert response.status_code == 500
    assert rows_with(target, marker) == []


def test_health_reports_unreachable_database(app_module, client, monkeypatch):
    port = closed_port()
    real_get_conn = app_module.get_conn

    def unreachable():
        # A real connection attempt to a port nobody listens on.
        return pycubrid.connect(
            host="127.0.0.1", port=port, database="testdb", user="dba", password=""
        )

    monkeypatch.setattr(app_module, "get_conn", unreachable)
    down = client.get("/health")

    assert down.status_code == 503
    assert down.json() == {"status": "error", "database": "unavailable"}
    assert "Traceback" not in down.text

    # The same app reports ok again once the database answers: not a static reply.
    monkeypatch.setattr(app_module, "get_conn", real_get_conn)
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
