from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def app_module():
    path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("quickstart_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("host", [None, "cubrid", "database.example"])
def test_connection_host(app_module, monkeypatch, host):
    if host is None:
        monkeypatch.delenv("CUBRID_HOST", raising=False)
    else:
        monkeypatch.setenv("CUBRID_HOST", host)
    connect = MagicMock()
    monkeypatch.setattr(app_module.pycubrid, "connect", connect)

    app_module.get_conn()

    assert connect.call_args.kwargs["host"] == (host or "localhost")


def test_compose_configures_container_host():
    compose = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    assert "CUBRID_HOST: cubrid" in compose.read_text()


def test_lifespan_initializes_table(app_module, monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app):
        assert (
            "CREATE TABLE IF NOT EXISTS cookbook_quickstart_items"
            in cursor.execute.call_args.args[0]
        )
        conn.commit.assert_called_once()
        cursor.close.assert_called_once()
        conn.close.assert_called_once()


@pytest.mark.parametrize("failure", ["cursor", "execute", "commit", "close"])
def test_startup_failure_cleans_up(app_module, monkeypatch, failure):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    target = conn if failure in {"cursor", "commit"} else cursor
    getattr(target, failure).side_effect = RuntimeError("database failure")
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with pytest.raises(RuntimeError, match="database failure"):
        with TestClient(app_module.app):
            pytest.fail("Startup failure must prevent serving requests")

    conn.rollback.assert_called_once()
    conn.close.assert_called_once()
    if failure != "cursor":
        cursor.close.assert_called_once()


@pytest.mark.parametrize(
    "method,path,payload,status,body",
    [
        ("GET", "/items", None, 200, [{"id": 1, "val": "example"}]),
        ("GET", "/items/1", None, 200, {"id": 1, "val": "example"}),
        ("POST", "/items", {"val": "example"}, 200, {"id": 1, "val": "example"}),
        ("GET", "/items/99", None, 404, {"detail": "Item not found"}),
    ],
)
def test_requests_close_resources(app_module, monkeypatch, method, path, payload, status, body):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [(1, "example")]
    cursor.fetchone.return_value = None if status == 404 else (1, "example")
    cursor.lastrowid = 1
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app) as client:
        conn.reset_mock()
        response = client.request(method, path, json=payload)

    assert response.status_code == status
    assert response.json() == body
    cursor.close.assert_called_once()
    conn.close.assert_called_once()
    if status == 404:
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
    else:
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()


@pytest.mark.parametrize(
    "method,path", [("GET", "/items"), ("GET", "/items/1"), ("POST", "/items")]
)
@pytest.mark.parametrize("failure", ["cursor", "execute", "commit"])
def test_request_failure_cleans_up(app_module, monkeypatch, method, path, failure):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = (1, "example")
    cursor.lastrowid = 1
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        conn.reset_mock()
        target = cursor if failure == "execute" else conn
        getattr(target, failure).side_effect = RuntimeError("database failure")
        response = client.request(method, path, json={"val": "example"})

    assert response.status_code == 500
    conn.rollback.assert_called_once()
    conn.close.assert_called_once()
    if failure != "cursor":
        cursor.close.assert_called_once()


def test_rollback_failure_still_closes_resources(app_module, monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        conn.reset_mock()
        cursor.execute.side_effect = RuntimeError("query failure")
        conn.rollback.side_effect = RuntimeError("rollback failure")
        response = client.get("/items")

    assert response.status_code == 500
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_health_checks_the_database(app_module, monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (1,)
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app) as client:
        conn.reset_mock()
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    cursor.execute.assert_called_once_with("SELECT 1 FROM db_root")
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.parametrize("failure", ["connect", "execute"])
def test_health_reports_database_failure(app_module, monkeypatch, failure):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    monkeypatch.setattr(app_module, "get_conn", lambda: conn)

    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        conn.reset_mock()
        if failure == "connect":
            connect = MagicMock(side_effect=OSError("secret detail"))
            monkeypatch.setattr(app_module, "get_conn", connect)
        else:
            cursor.execute.side_effect = RuntimeError("secret detail")
        response = client.get("/health")

    # A controlled body: no exception text or traceback reaches the client.
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert "secret detail" not in response.text
    if failure == "execute":
        conn.rollback.assert_called_once()
        cursor.close.assert_called_once()
        conn.close.assert_called_once()
