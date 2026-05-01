from __future__ import annotations

import threading
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import database
import main
from database import Base, get_db
from models import EventStore


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    database.engine = engine
    database.SessionLocal = test_session_local
    main.engine = engine

    def override_get_db() -> Generator[Session, None, None]:
        db = test_session_local()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _open_account(client: TestClient, account_id: str = "acct-1") -> dict[str, object]:
    response = client.post(
        "/accounts",
        json={"account_id": account_id, "owner_name": "Alice"},
    )
    assert response.status_code == 201
    return response.json()


def test_open_deposit_withdraw_flow(client: TestClient) -> None:
    _open_account(client)

    deposit_response = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 5000, "expected_sequence_no": 1},
    )
    assert deposit_response.status_code == 200

    withdraw_response = client.post(
        "/accounts/acct-1/withdraw",
        json={"amount_cents": 1200, "expected_sequence_no": 2},
    )
    assert withdraw_response.status_code == 200

    account_response = client.get("/accounts/acct-1")
    assert account_response.status_code == 200
    account_data = account_response.json()
    assert account_data["balance_cents"] == 3800
    assert account_data["last_sequence_no"] == 3

    events_response = client.get("/accounts/acct-1/events")
    assert events_response.status_code == 200
    events = events_response.json()
    assert [event["event_type"] for event in events] == [
        "AccountOpened",
        "MoneyDeposited",
        "MoneyWithdrawn",
    ]
    assert [event["sequence_no"] for event in events] == [1, 2, 3]


def test_concurrent_deposit_conflict(client: TestClient) -> None:
    _open_account(client)

    # First deposit succeeds
    r1 = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 1000, "expected_sequence_no": 1},
    )
    assert r1.status_code == 200

    # Second deposit with same expected_sequence_no gets 409 (stale)
    r2 = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 500, "expected_sequence_no": 1},
    )
    assert r2.status_code == 409


def test_overdraft_rejected(client: TestClient) -> None:
    _open_account(client)
    deposit_response = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 2000, "expected_sequence_no": 1},
    )
    assert deposit_response.status_code == 200

    withdraw_response = client.post(
        "/accounts/acct-1/withdraw",
        json={"amount_cents": 5000, "expected_sequence_no": 2},
    )
    assert withdraw_response.status_code == 422

    events_response = client.get("/accounts/acct-1/events")
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 2


def test_snapshot_and_rebuild(client: TestClient) -> None:
    _open_account(client)
    response = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 3000, "expected_sequence_no": 1},
    )
    assert response.status_code == 200

    snapshot_response = client.post("/accounts/acct-1/snapshot")
    assert snapshot_response.status_code == 200
    snapshot_data = snapshot_response.json()
    assert snapshot_data["last_sequence_no"] == 2

    withdraw_response = client.post(
        "/accounts/acct-1/withdraw",
        json={"amount_cents": 500, "expected_sequence_no": 2},
    )
    assert withdraw_response.status_code == 200

    rebuild_response = client.post(
        "/accounts/acct-1/rebuild",
        json={"from_scratch": 0},
    )
    assert rebuild_response.status_code == 200
    rebuilt = rebuild_response.json()
    assert rebuilt["balance_cents"] == 2500
    assert rebuilt["last_sequence_no"] == 3


def test_full_rebuild_from_scratch(client: TestClient) -> None:
    _open_account(client)
    dep1 = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 4000, "expected_sequence_no": 1},
    )
    dep2 = client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 600, "expected_sequence_no": 2},
    )
    wd1 = client.post(
        "/accounts/acct-1/withdraw",
        json={"amount_cents": 1000, "expected_sequence_no": 3},
    )
    assert dep1.status_code == 200
    assert dep2.status_code == 200
    assert wd1.status_code == 200

    rebuild_response = client.post(
        "/accounts/acct-1/rebuild",
        json={"from_scratch": 1},
    )
    assert rebuild_response.status_code == 200
    rebuilt = rebuild_response.json()
    assert rebuilt["balance_cents"] == 3600
    assert rebuilt["last_sequence_no"] == 4


def test_duplicate_account_409(client: TestClient) -> None:
    first = client.post(
        "/accounts",
        json={"account_id": "acct-dup", "owner_name": "Bob"},
    )
    second = client.post(
        "/accounts",
        json={"account_id": "acct-dup", "owner_name": "Bob"},
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_read_model_sequence_matches_tail(client: TestClient) -> None:
    _open_account(client)
    client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 111, "expected_sequence_no": 1},
    )
    client.post(
        "/accounts/acct-1/deposit",
        json={"amount_cents": 222, "expected_sequence_no": 2},
    )
    client.post(
        "/accounts/acct-1/withdraw",
        json={"amount_cents": 100, "expected_sequence_no": 3},
    )

    account_response = client.get("/accounts/acct-1")
    assert account_response.status_code == 200
    read_model_seq = account_response.json()["last_sequence_no"]

    with database.SessionLocal() as db:
        tail = db.scalar(
            select(EventStore.sequence_no)
            .where(EventStore.aggregate_id == "acct-1")
            .order_by(EventStore.sequence_no.desc())
            .limit(1)
        )

    assert read_model_seq == tail
