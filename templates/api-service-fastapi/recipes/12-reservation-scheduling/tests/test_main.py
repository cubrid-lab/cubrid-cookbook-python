from __future__ import annotations

import os
import sys
import importlib
from collections.abc import Generator
from pathlib import Path

from httpx import Response
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

RECIPE_ROOT = Path(__file__).resolve().parent.parent
if str(RECIPE_ROOT) not in sys.path:
    sys.path.insert(0, str(RECIPE_ROOT))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

database = importlib.import_module("database")
main_module = importlib.import_module("main")
Base = database.Base
get_db = database.get_db
app = main_module.app


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


def _create_resource(client: TestClient) -> None:
    response = client.post(
        "/resources",
        json={"resource_key": "room-a", "name": "Room A", "slot_minutes": 30},
    )
    assert response.status_code == 201


def _create_reservation(
    client: TestClient,
    reservation_key: str,
    requester_id: str,
    start_at: str,
    end_at: str,
) -> Response:
    return client.post(
        "/reservations",
        json={
            "reservation_key": reservation_key,
            "resource_key": "room-a",
            "requester_id": requester_id,
            "start_at": start_at,
            "end_at": end_at,
        },
    )


def test_non_overlapping_both_succeed(client: TestClient) -> None:
    _create_resource(client)
    first = _create_reservation(client, "r1", "u1", "2026-01-01T10:00:00", "2026-01-01T10:30:00")
    second = _create_reservation(client, "r2", "u2", "2026-01-01T10:30:00", "2026-01-01T11:00:00")
    assert first.status_code == 201
    assert second.status_code == 201


def test_overlapping_rejected_409(client: TestClient) -> None:
    _create_resource(client)
    first = _create_reservation(client, "r1", "u1", "2026-01-01T10:00:00", "2026-01-01T11:00:00")
    second = _create_reservation(client, "r2", "u2", "2026-01-01T10:30:00", "2026-01-01T10:45:00")
    assert first.status_code == 201
    assert second.status_code == 409


def test_concurrent_booking_one_wins(client: TestClient) -> None:
    _create_resource(client)
    first = _create_reservation(client, "r1", "u1", "2026-01-01T09:00:00", "2026-01-01T10:00:00")
    second = _create_reservation(client, "r2", "u2", "2026-01-01T09:00:00", "2026-01-01T10:00:00")
    statuses = {first.status_code, second.status_code}
    assert statuses == {201, 409}


def test_cancel_promotes_waitlist(client: TestClient) -> None:
    _create_resource(client)
    booked = _create_reservation(client, "r1", "u1", "2026-01-01T12:00:00", "2026-01-01T13:00:00")
    assert booked.status_code == 201

    wait_1 = client.post(
        "/resources/room-a/waitlist",
        json={
            "requester_id": "u2",
            "desired_start_at": "2026-01-01T12:00:00",
            "desired_end_at": "2026-01-01T13:00:00",
        },
    )
    wait_2 = client.post(
        "/resources/room-a/waitlist",
        json={
            "requester_id": "u3",
            "desired_start_at": "2026-01-01T12:15:00",
            "desired_end_at": "2026-01-01T12:45:00",
        },
    )
    assert wait_1.status_code == 201
    assert wait_2.status_code == 201

    cancelled = client.post("/reservations/r1/cancel")
    assert cancelled.status_code == 200
    payload = cancelled.json()
    assert payload["state"] == "cancelled"
    assert payload["promoted_reservation_key"] == "promoted-1"

    waitlist = client.get("/resources/room-a/waitlist")
    assert waitlist.status_code == 200
    entries = waitlist.json()
    assert entries[0]["state"] == "promoted"
    assert entries[1]["state"] == "waiting"


def test_cancel_no_matching_waitlist(client: TestClient) -> None:
    _create_resource(client)
    booked = _create_reservation(client, "r1", "u1", "2026-01-01T15:00:00", "2026-01-01T16:00:00")
    assert booked.status_code == 201

    blocking = _create_reservation(client, "r2", "u9", "2026-01-01T16:00:00", "2026-01-01T17:00:00")
    assert blocking.status_code == 201

    wait = client.post(
        "/resources/room-a/waitlist",
        json={
            "requester_id": "u2",
            "desired_start_at": "2026-01-01T16:15:00",
            "desired_end_at": "2026-01-01T16:30:00",
        },
    )
    assert wait.status_code == 201

    cancelled = client.post("/reservations/r1/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["promoted_reservation_key"] is None


def test_invalid_interval_400(client: TestClient) -> None:
    _create_resource(client)
    invalid = _create_reservation(client, "r1", "u1", "2026-01-01T11:00:00", "2026-01-01T11:00:00")
    assert invalid.status_code == 400


def test_list_reservations_in_window(client: TestClient) -> None:
    _create_resource(client)
    _create_reservation(client, "r1", "u1", "2026-01-01T08:00:00", "2026-01-01T08:30:00")
    _create_reservation(client, "r2", "u2", "2026-01-01T09:00:00", "2026-01-01T09:30:00")
    _create_reservation(client, "r3", "u3", "2026-01-01T10:00:00", "2026-01-01T10:30:00")

    listed = client.get(
        "/resources/room-a/reservations",
        params={"from_at": "2026-01-01T08:15:00", "to_at": "2026-01-01T09:45:00"},
    )
    assert listed.status_code == 200
    keys = [item["reservation_key"] for item in listed.json()]
    assert keys == ["r1", "r2"]
