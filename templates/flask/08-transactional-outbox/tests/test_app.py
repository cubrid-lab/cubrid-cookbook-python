# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys
from datetime import datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from flask import Flask
from sqlalchemy import update

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

create_app = importlib.import_module("app").create_app
_models = importlib.import_module("models")
OutboxMessage = _models.OutboxMessage
db = importlib.import_module("database").db


@pytest.fixture
def app(tmp_path: Path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}", "SQLALCHEMY_TRACK_MODIFICATIONS": False})


@pytest.fixture
def httpx_client(app):
    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client

def _create_invoice(
    httpx_client: httpx.Client,
    customer_email: str = "buyer@example.com",
    total_cents: int = 9900,
) -> dict[str, Any]:
    response = httpx_client.post(
        "/api/invoices",
        json={"customer_email": customer_email, "total_cents": total_cents},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_invoice_creates_outbox_message(app: Flask, httpx_client: httpx.Client) -> None:
    invoice = _create_invoice(httpx_client)
    assert invoice["status"] == "draft"
    assert invoice["total_cents"] == 9900

    response = httpx_client.get("/api/outbox?status=pending")
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["event_type"] == "invoice.created"
    assert messages[0]["aggregate_id"] == invoice["id"]
    assert messages[0]["idempotency_key"] == f"invoice-created-{invoice['id']}"


def test_lease_returns_pending_messages(app: Flask, httpx_client: httpx.Client) -> None:
    _create_invoice(httpx_client)
    _create_invoice(httpx_client, customer_email="other@example.com")

    response = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 5, "processor_id": "worker-1"},
    )
    assert response.status_code == 200
    leased = response.json()
    assert len(leased) == 2
    for msg in leased:
        assert msg["attempts"] == 1
        assert msg["leased_until"] is not None


def test_ack_sets_status_to_sent(app: Flask, httpx_client: httpx.Client) -> None:
    _create_invoice(httpx_client)

    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg = lease_resp.json()[0]

    ack_resp = httpx_client.post(f"/api/outbox/{msg['id']}/ack", json={"processor_id": "worker-1"})
    assert ack_resp.status_code == 200
    acked = ack_resp.json()
    assert acked["status"] == "sent"
    assert acked["sent_at"] is not None


def test_fail_with_retries_requeues(app: Flask, httpx_client: httpx.Client) -> None:
    _create_invoice(httpx_client)

    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg = lease_resp.json()[0]

    fail_resp = httpx_client.post(
        f"/api/outbox/{msg['id']}/fail",
        json={"processor_id": "worker-1", "error": "connection timeout"},
    )
    assert fail_resp.status_code == 200
    failed = fail_resp.json()
    assert failed["status"] == "pending"
    assert failed["last_error"] == "connection timeout"
    assert failed["next_attempt_at"] is not None


def test_fail_three_times_dead_letters(app: Flask, httpx_client: httpx.Client) -> None:
    _create_invoice(httpx_client)

    # Lease attempt 1
    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg = lease_resp.json()[0]
    httpx_client.post(
        f"/api/outbox/{msg['id']}/fail", json={"processor_id": "worker-1", "error": "err1"}
    )

    # Need to advance next_attempt_at for subsequent leases
    with app.app_context():
        db.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg["id"])
            .values(next_attempt_at=datetime.utcnow() - timedelta(seconds=1))
        )
        db.session.commit()

    # Lease attempt 2
    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg2 = lease_resp.json()[0]
    httpx_client.post(
        f"/api/outbox/{msg2['id']}/fail", json={"processor_id": "worker-1", "error": "err2"}
    )

    with app.app_context():
        db.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg["id"])
            .values(next_attempt_at=datetime.utcnow() - timedelta(seconds=1))
        )
        db.session.commit()

    # Lease attempt 3
    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg3 = lease_resp.json()[0]
    fail_resp = httpx_client.post(
        f"/api/outbox/{msg3['id']}/fail", json={"processor_id": "worker-1", "error": "err3"}
    )
    assert fail_resp.status_code == 200
    dead = fail_resp.json()
    assert dead["status"] == "dead_letter"


def test_send_invoice_creates_outbox_message(app: Flask, httpx_client: httpx.Client) -> None:
    invoice = _create_invoice(httpx_client)

    send_resp = httpx_client.post(f"/api/invoices/{invoice['id']}/send")
    assert send_resp.status_code == 200
    sent = send_resp.json()
    assert sent["status"] == "sent"

    # Should now have 2 outbox messages
    outbox_resp = httpx_client.get("/api/outbox")
    messages = outbox_resp.json()
    assert len(messages) == 2
    event_types = [m["event_type"] for m in messages]
    assert "invoice.created" in event_types
    assert "invoice.sent" in event_types


def test_duplicate_send_returns_409(app: Flask, httpx_client: httpx.Client) -> None:
    invoice = _create_invoice(httpx_client)

    resp1 = httpx_client.post(f"/api/invoices/{invoice['id']}/send")
    assert resp1.status_code == 200

    resp2 = httpx_client.post(f"/api/invoices/{invoice['id']}/send")
    assert resp2.status_code == 409
