from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

RECIPE_ROOT = Path(__file__).resolve().parent.parent
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import routes
from database import Base, get_db
from main import app


class FrozenTime:
    def __init__(self, start: datetime):
        self.current = start

    def utcnow(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    session = session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> FrozenTime:
    clock = FrozenTime(datetime(2026, 1, 1, 0, 0, 0))
    monkeypatch.setattr(routes, "utcnow", clock.utcnow)
    return clock


def _create_client(client: TestClient, **overrides: int | str) -> None:
    payload = {
        "client_key": "alpha",
        "limit_per_window": 5,
        "window_seconds": 10,
        "burst_allowance": 0,
    }
    payload.update(overrides)
    response = client.post("/clients", json=payload)
    assert response.status_code == 201


def test_consume_under_limit(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client)

    first = client.post("/clients/alpha/consume", json={"cost": 1})
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "5"
    assert first.headers["X-RateLimit-Remaining"] == "4"

    second = client.post("/clients/alpha/consume", json={"cost": 2})
    assert second.status_code == 200
    assert second.json()["remaining"] == 2


def test_consume_over_limit_429(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client, limit_per_window=2)

    ok = client.post("/clients/alpha/consume", json={"cost": 2})
    assert ok.status_code == 200

    blocked = client.post("/clients/alpha/consume", json={"cost": 1})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_window_rotation(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client, limit_per_window=10, window_seconds=10)
    consumed = client.post("/clients/alpha/consume", json={"cost": 4})
    assert consumed.status_code == 200

    frozen_time.advance(10)
    quota = client.get("/clients/alpha/quota")
    assert quota.status_code == 200
    data = quota.json()
    assert data["current_count"] == 0
    assert data["previous_count"] == 4


def test_large_gap_clears_previous(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client, limit_per_window=10, window_seconds=10)
    consumed = client.post("/clients/alpha/consume", json={"cost": 3})
    assert consumed.status_code == 200

    frozen_time.advance(21)
    quota = client.get("/clients/alpha/quota")
    assert quota.status_code == 200
    data = quota.json()
    assert data["previous_count"] == 0
    assert data["weighted_count"] == 0


def test_concurrent_consume_version_safety(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client, limit_per_window=10)

    first = client.post("/clients/alpha/consume", json={"cost": 2})
    assert first.status_code == 200

    stale_reset = client.post("/clients/alpha/reset", json={"expected_version": 1})
    assert stale_reset.status_code == 409


def test_policy_update_stale_version_409(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client)

    updated = client.put(
        "/clients/alpha/policy",
        json={
            "limit_per_window": 6,
            "window_seconds": 10,
            "burst_allowance": 1,
            "expected_version": 1,
        },
    )
    assert updated.status_code == 200

    stale = client.put(
        "/clients/alpha/policy",
        json={
            "limit_per_window": 7,
            "window_seconds": 10,
            "burst_allowance": 2,
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409


def test_burst_allowance(client: TestClient, frozen_time: FrozenTime) -> None:
    _create_client(client, limit_per_window=5, burst_allowance=2)

    allowed = client.post("/clients/alpha/consume", json={"cost": 7})
    assert allowed.status_code == 200
    assert allowed.json()["remaining"] == 0

    blocked = client.post("/clients/alpha/consume", json={"cost": 1})
    assert blocked.status_code == 429
