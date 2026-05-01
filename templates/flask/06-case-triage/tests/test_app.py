# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys
from datetime import datetime, timedelta
from typing import TypedDict, cast

import httpx
import pytest
from flask import Flask
from sqlalchemy import select, update

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app
db = importlib.import_module("database").db
_models = importlib.import_module("models")
ReviewCase = _models.ReviewCase


@pytest.fixture
def app(tmp_path: Path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}", "SQLALCHEMY_TRACK_MODIFICATIONS": False})


@pytest.fixture
def httpx_client(app):
    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client

class CasePayload(TypedDict):
    id: int
    customer_email: str
    subject: str
    body: str
    priority: int
    status: str
    claimed_by: str | None


def _create_case(
    httpx_client: httpx.Client,
    customer_email: str = "alice@example.com",
    subject: str = "Payment issue",
    body: str = "Unable to complete checkout",
    priority: int = 0,
) -> CasePayload:
    response = httpx_client.post(
        "/api/cases",
        json={
            "customer_email": customer_email,
            "subject": subject,
            "body": body,
            "priority": priority,
        },
    )
    assert response.status_code == 201
    return cast(CasePayload, response.json())


def _claim_case(httpx_client: httpx.Client, case_id: int, agent: str) -> CasePayload:
    response = httpx_client.post(f"/api/cases/{case_id}/claim", json={"agent": agent})
    assert response.status_code == 200
    return cast(CasePayload, response.json())


def test_create_case_and_retrieve(httpx_client: httpx.Client) -> None:
    created_case = _create_case(httpx_client, subject="Refund request", priority=3)

    response = httpx_client.get(f"/api/cases/{created_case['id']}")
    assert response.status_code == 200

    payload = cast(dict[str, object], response.json())
    assert payload["id"] == created_case["id"]
    assert payload["subject"] == "Refund request"
    assert payload["priority"] == 3
    assert payload["status"] == "new"
    assert payload["notes"] == []


def test_claim_case_successfully(httpx_client: httpx.Client) -> None:
    created_case = _create_case(httpx_client)
    claimed_case = _claim_case(httpx_client, created_case["id"], "agent-1")

    assert claimed_case["status"] == "claimed"
    assert claimed_case["claimed_by"] == "agent-1"


def test_reject_double_claim(httpx_client: httpx.Client) -> None:
    created_case = _create_case(httpx_client)
    _ = _claim_case(httpx_client, created_case["id"], "agent-1")

    response = httpx_client.post(
        f"/api/cases/{created_case['id']}/claim", json={"agent": "agent-2"}
    )
    assert response.status_code == 409
    assert response.json()["error"] == "Case already claimed and lease not expired."


def test_claim_expired_lease(httpx_client: httpx.Client, app: Flask) -> None:
    created_case = _create_case(httpx_client)
    _ = _claim_case(httpx_client, created_case["id"], "agent-1")

    with app.app_context():
        _ = db.session.execute(
            update(ReviewCase)
            .where(ReviewCase.id == created_case["id"])
            .values(lease_expires_at=datetime.utcnow() - timedelta(minutes=1))
        )
        db.session.commit()

    response = httpx_client.post(
        f"/api/cases/{created_case['id']}/claim", json={"agent": "agent-2"}
    )
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["status"] == "claimed"
    assert payload["claimed_by"] == "agent-2"


def test_release_and_reclaim(httpx_client: httpx.Client) -> None:
    created_case = _create_case(httpx_client)
    _ = _claim_case(httpx_client, created_case["id"], "agent-1")

    release_response = httpx_client.post(
        f"/api/cases/{created_case['id']}/release", json={"agent": "agent-1"}
    )
    assert release_response.status_code == 200
    released_payload = cast(dict[str, object], release_response.json())
    assert released_payload["status"] == "new"
    assert released_payload["claimed_by"] is None

    reclaim_response = httpx_client.post(
        f"/api/cases/{created_case['id']}/claim", json={"agent": "agent-2"}
    )
    assert reclaim_response.status_code == 200
    assert reclaim_response.json()["claimed_by"] == "agent-2"


def test_claim_next_picks_highest_priority_first(httpx_client: httpx.Client) -> None:
    _ = _create_case(httpx_client, subject="Low", priority=1)
    high = _create_case(httpx_client, subject="High", priority=10)
    _ = _create_case(httpx_client, subject="Medium", priority=5)

    response = httpx_client.post("/api/cases/claim-next", json={"agent": "agent-queue"})
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["id"] == high["id"]
    assert payload["priority"] == 10
    assert payload["claimed_by"] == "agent-queue"


def test_resolve_case_and_verify_status(httpx_client: httpx.Client, app: Flask) -> None:
    created_case = _create_case(httpx_client)
    _ = _claim_case(httpx_client, created_case["id"], "resolver-1")

    response = httpx_client.post(
        f"/api/cases/{created_case['id']}/resolve",
        json={"agent": "resolver-1", "resolution_note": "Refund approved"},
    )
    assert response.status_code == 200

    payload = cast(dict[str, object], response.json())
    assert payload["status"] == "resolved"
    assert payload["resolved_at"] is not None

    with app.app_context():
        review_case = db.session.execute(
            select(ReviewCase).where(ReviewCase.id == created_case["id"])
        ).scalar_one()
        assert review_case.status == "resolved"
        assert len(review_case.notes) == 1
        assert review_case.notes[0].body == "Refund approved"
