# pyright: reportCallIssue=false
from __future__ import annotations

from pathlib import Path
import sys
from datetime import timedelta
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
naive_utc_now = importlib.import_module("app").naive_utc_now
_models = importlib.import_module("models")
OutboxMessage = _models.OutboxMessage
db = importlib.import_module("database").db


@pytest.fixture
def app(database_config: dict[str, object]):
    return create_app(
        {
            "TESTING": True,
            **database_config,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )


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

    ack_resp = httpx_client.post(
        f"/api/outbox/{msg['id']}/ack",
        json={"processor_id": "worker-1", "lease_attempt": msg["attempts"]},
    )
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
        json={
            "processor_id": "worker-1",
            "lease_attempt": msg["attempts"],
            "error": "connection timeout",
        },
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
        f"/api/outbox/{msg['id']}/fail",
        json={"processor_id": "worker-1", "lease_attempt": msg["attempts"], "error": "err1"},
    )

    # Need to advance next_attempt_at for subsequent leases
    with app.app_context():
        db.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg["id"])
            .values(next_attempt_at=naive_utc_now() - timedelta(seconds=1))
        )
        db.session.commit()

    # Lease attempt 2
    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg2 = lease_resp.json()[0]
    httpx_client.post(
        f"/api/outbox/{msg2['id']}/fail",
        json={"processor_id": "worker-1", "lease_attempt": msg2["attempts"], "error": "err2"},
    )

    with app.app_context():
        db.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg["id"])
            .values(next_attempt_at=naive_utc_now() - timedelta(seconds=1))
        )
        db.session.commit()

    # Lease attempt 3
    lease_resp = httpx_client.post(
        "/api/outbox/lease",
        json={"max_messages": 1, "processor_id": "worker-1"},
    )
    msg3 = lease_resp.json()[0]
    fail_resp = httpx_client.post(
        f"/api/outbox/{msg3['id']}/fail",
        json={"processor_id": "worker-1", "lease_attempt": msg3["attempts"], "error": "err3"},
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


def _release_on_first_write(app: Flask, message_id: int, holder: str = "worker-2"):
    """Expire worker-1's lease and give it to ``holder`` just before the app's first write.

    The re-lease commits on its own connection after the endpoint has read the
    message (and seen worker-1's lease), so it models a lease that expired and was
    taken again (by another processor, or by worker-1 itself with a new attempt
    number) while worker-1 was still finishing its work.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import NullPool

    pending = [True]
    with app.app_context():
        engine = db.engine
        url = engine.url

    def release_before_write(conn, cursor, statement, parameters, context, executemany):
        if pending and statement.lstrip().upper().startswith(("UPDATE", "INSERT")):
            pending.clear()
            other = create_engine(url, poolclass=NullPool)
            try:
                with other.begin() as connection:
                    connection.execute(
                        update(OutboxMessage)
                        .where(OutboxMessage.id == message_id)
                        .values(
                            leased_by=holder,
                            leased_until=naive_utc_now() + timedelta(minutes=5),
                            attempts=OutboxMessage.attempts + 1,
                        )
                    )
            finally:
                other.dispose()

    event.listen(engine, "before_cursor_execute", release_before_write)
    return engine, release_before_write, pending


@pytest.mark.parametrize("holder", ["worker-2", "worker-1"])
@pytest.mark.parametrize(
    ("action", "payload"),
    [("ack", {}), ("fail", {"error": "late failure"})],
)
def test_settling_a_lease_taken_again_after_the_read_conflicts(
    app: Flask, httpx_client: httpx.Client, action: str, payload: dict[str, str], holder: str
) -> None:
    from sqlalchemy import event

    _create_invoice(httpx_client)
    lease_resp = httpx_client.post(
        "/api/outbox/lease", json={"max_messages": 1, "processor_id": "worker-1"}
    )
    msg = lease_resp.json()[0]

    engine, listener, pending = _release_on_first_write(app, msg["id"], holder)
    try:
        response = httpx_client.post(
            f"/api/outbox/{msg['id']}/{action}",
            json={"processor_id": "worker-1", "lease_attempt": msg["attempts"], **payload},
        )
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert not pending, "the endpoint wrote nothing"
    assert response.status_code == 409
    current = httpx_client.get(f"/api/outbox/{msg['id']}").json()
    # The new lease is untouched: still pending, leased by its holder, attempt 2.
    assert (current["status"], current["leased_by"], current["attempts"]) == (
        "pending",
        holder,
        2,
    )
    assert current["attempts_list"] == []


def _expire_lease(app: Flask, message_id: int) -> None:
    with app.app_context():
        db.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(leased_until=naive_utc_now() - timedelta(seconds=1))
        )
        db.session.commit()


@pytest.mark.parametrize(
    ("action", "payload"),
    [("ack", {}), ("fail", {"error": "late failure"})],
)
def test_stale_request_cannot_settle_a_newer_lease_of_the_same_processor(
    app: Flask, httpx_client: httpx.Client, action: str, payload: dict[str, str]
) -> None:
    _create_invoice(httpx_client)
    lease = {"max_messages": 1, "processor_id": "worker-1"}
    first = httpx_client.post("/api/outbox/lease", json=lease).json()[0]
    assert first["attempts"] == 1

    # worker-1's first lease expires and worker-1 leases the message again
    # (attempt 2) before its first, stale request arrives.
    _expire_lease(app, first["id"])
    second = httpx_client.post("/api/outbox/lease", json=lease).json()[0]
    assert (second["id"], second["attempts"]) == (first["id"], 2)

    stale = httpx_client.post(
        f"/api/outbox/{first['id']}/{action}",
        json={"processor_id": "worker-1", "lease_attempt": first["attempts"], **payload},
    )

    assert stale.status_code == 409
    assert "stale" in stale.json()["error"]
    current = httpx_client.get(f"/api/outbox/{first['id']}").json()
    assert (current["status"], current["leased_by"], current["attempts"]) == (
        "pending",
        "worker-1",
        2,
    )
    assert current["attempts_list"] == []

    # The current lease still settles normally.
    fresh = httpx_client.post(
        f"/api/outbox/{first['id']}/{action}",
        json={"processor_id": "worker-1", "lease_attempt": second["attempts"], **payload},
    )
    assert fresh.status_code == 200


@pytest.mark.parametrize("action", ["ack", "fail"])
@pytest.mark.parametrize(
    ("lease_attempt", "status"),
    [(None, 409), ("1", 400), (True, 400), (1.0, 400)],
    ids=["missing", "string", "bool", "float"],
)
def test_settling_requires_an_integer_lease_attempt(
    app: Flask, httpx_client: httpx.Client, action: str, lease_attempt: object, status: int
) -> None:
    # A missing lease_attempt does not show a lease (409); a malformed one is a bad
    # request (400). Either way the lease is left as it was.
    _create_invoice(httpx_client)
    msg = httpx_client.post(
        "/api/outbox/lease", json={"max_messages": 1, "processor_id": "worker-1"}
    ).json()[0]
    body: dict[str, object] = {"processor_id": "worker-1"}
    if lease_attempt is not None:
        body["lease_attempt"] = lease_attempt

    response = httpx_client.post(f"/api/outbox/{msg['id']}/{action}", json=body)

    assert response.status_code == status
    assert "lease_attempt" in response.json()["error"]
    assert httpx_client.get(f"/api/outbox/{msg['id']}").json()["leased_by"] == "worker-1"
