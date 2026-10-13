from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

RECIPE_ROOT = Path(__file__).resolve().parent.parent
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

import routes
from database import get_db
from main import app


class FrozenTime:
    def __init__(self, start: datetime):
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = session_local()
    try:
        yield session
    finally:
        session.close()


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
    monkeypatch.setattr(routes, "naive_utc_now", clock.now)
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


def test_real_clock_is_naive_and_comparable_with_stored_values() -> None:
    now = routes.naive_utc_now()
    stored = datetime(2026, 1, 1, 0, 0, 0)  # naive, as read back from a DATETIME column
    assert now.tzinfo is None
    assert (now - stored).total_seconds() > 0


def _stored_window(engine: Engine) -> tuple[int, int, int]:
    """Read (current_count, previous_count, version) from the database itself."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT current_count, previous_count, version FROM cookbook_client_rate_windows")
        ).one()
    return row[0], row[1], row[2]


def test_rotation_stores_the_new_window_count(
    client: TestClient, frozen_time: FrozenTime, engine: Engine
) -> None:
    _create_client(client, limit_per_window=10, window_seconds=10)
    assert client.post("/clients/alpha/consume", json={"cost": 4}).status_code == 200

    frozen_time.advance(11)
    consumed = client.post("/clients/alpha/consume", json={"cost": 1})

    assert consumed.status_code == 200
    # The new window holds only the new cost; the old 4 moved to previous_count.
    assert _stored_window(engine)[:2] == (1, 4)


def test_reset_rejects_a_consume_that_landed_after_its_read(
    client: TestClient, frozen_time: FrozenTime, engine: Engine
) -> None:
    _create_client(client, limit_per_window=10)
    assert client.post("/clients/alpha/consume", json={"cost": 2}).status_code == 200
    version = client.get("/clients/alpha/quota").json()["window_version"]

    # Run a consume (+3, new version) once, just before the reset's own UPDATE and
    # after the reset has read the window with the version it expects.
    pending = [True]

    def concurrent_consume(conn, cursor, statement, parameters, context, executemany):
        if pending and statement.lstrip().upper().startswith("UPDATE COOKBOOK_CLIENT_RATE_WINDOWS"):
            pending.clear()
            cursor.execute(
                "UPDATE cookbook_client_rate_windows"
                " SET current_count = current_count + 3, version = version + 1"
            )

    event.listen(engine, "before_cursor_execute", concurrent_consume)
    try:
        reset = client.post("/clients/alpha/reset", json={"expected_version": version})
    finally:
        event.remove(engine, "before_cursor_execute", concurrent_consume)

    assert not pending, "the reset sent no UPDATE"

    assert reset.status_code == 409
    # Nothing was cleared. The simulated consume ran on the reset's own connection,
    # so the reset's rollback undoes it too and the window is as it was before.
    assert _stored_window(engine) == (2, 0, version)
