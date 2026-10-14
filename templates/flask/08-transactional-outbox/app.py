# pyright: reportCallIssue=false
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

import importlib

_models = importlib.import_module("models")
Invoice = _models.Invoice
OutboxAttempt = _models.OutboxAttempt
OutboxMessage = _models.OutboxMessage
db = importlib.import_module("database").db

outbox_bp = Blueprint("outbox", __name__, url_prefix="/api")


def naive_utc_now() -> datetime:
    """Return the current UTC time without tzinfo.

    The DateTime columns store naive UTC values, so everything read back from the
    database is naive. Comparing that with an aware datetime raises TypeError, so
    any "now" compared against these columns must be naive too.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_payload() -> Mapping[str, object]:
    payload_value = request.get_json(silent=True)
    if isinstance(payload_value, dict):
        return cast(dict[str, object], payload_value)
    return {}


@outbox_bp.post("/invoices")
def create_invoice():
    payload = _json_payload()
    customer_email = str(payload.get("customer_email", "")).strip()
    total_cents_value = payload.get("total_cents")

    if not customer_email:
        return jsonify({"error": "customer_email is required"}), 400
    if isinstance(total_cents_value, bool) or not isinstance(total_cents_value, int):
        return jsonify({"error": "total_cents must be an integer"}), 400
    if total_cents_value < 0:
        return jsonify({"error": "total_cents cannot be negative"}), 400

    invoice = Invoice()
    invoice.customer_email = customer_email
    invoice.total_cents = total_cents_value
    invoice.status = "draft"

    db.session.add(invoice)
    db.session.flush()

    outbox_message = OutboxMessage()
    outbox_message.topic = "invoices"
    outbox_message.aggregate_type = "invoice"
    outbox_message.aggregate_id = invoice.id
    outbox_message.event_type = "invoice.created"
    outbox_message.payload = json.dumps(invoice.to_dict())
    outbox_message.idempotency_key = f"invoice-created-{invoice.id}"
    db.session.add(outbox_message)

    db.session.commit()
    return jsonify(invoice.to_dict()), 201


@outbox_bp.post("/invoices/<int:invoice_id>/send")
def send_invoice(invoice_id: int):
    invoice = db.session.get(Invoice, invoice_id)
    if invoice is None:
        return jsonify({"error": "Invoice not found."}), 404
    if invoice.status == "sent":
        return jsonify({"error": "Invoice already sent."}), 409

    now = naive_utc_now()
    invoice.status = "sent"
    invoice.sent_at = now

    outbox_message = OutboxMessage()
    outbox_message.topic = "invoices"
    outbox_message.aggregate_type = "invoice"
    outbox_message.aggregate_id = invoice.id
    outbox_message.event_type = "invoice.sent"
    outbox_message.payload = json.dumps(invoice.to_dict())
    outbox_message.idempotency_key = f"invoice-sent-{invoice.id}"
    db.session.add(outbox_message)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Outbox idempotency key already exists."}), 409

    return jsonify(invoice.to_dict())


@outbox_bp.get("/outbox")
def list_outbox_messages():
    stmt = select(OutboxMessage).order_by(OutboxMessage.id.asc())
    status = request.args.get("status")
    if status is not None:
        stmt = stmt.where(OutboxMessage.status == status)

    messages = db.session.execute(stmt).scalars().all()
    return jsonify([message.to_dict() for message in messages])


@outbox_bp.post("/outbox/lease")
def lease_outbox_messages():
    payload = _json_payload()
    max_messages_value = payload.get("max_messages", 5)
    processor_id = str(payload.get("processor_id", "")).strip()

    if isinstance(max_messages_value, bool) or not isinstance(max_messages_value, int):
        return jsonify({"error": "max_messages must be an integer"}), 400
    if max_messages_value <= 0:
        return jsonify({"error": "max_messages must be greater than zero"}), 400
    if not processor_id:
        return jsonify({"error": "processor_id is required"}), 400

    now = naive_utc_now()
    lease_until = now + timedelta(minutes=5)
    messages = (
        db.session.execute(
            select(OutboxMessage)
            .where(
                OutboxMessage.status == "pending",
                OutboxMessage.next_attempt_at <= now,
                or_(OutboxMessage.leased_until.is_(None), OutboxMessage.leased_until <= now),
            )
            .order_by(OutboxMessage.id.asc())
            .limit(max_messages_value)
        )
        .scalars()
        .all()
    )

    claimed_ids: list[int] = []
    for message in messages:
        updated = (
            db.session.query(OutboxMessage)
            .filter(
                OutboxMessage.id == message.id,
                OutboxMessage.status == "pending",
                OutboxMessage.next_attempt_at <= now,
                or_(OutboxMessage.leased_until.is_(None), OutboxMessage.leased_until <= now),
            )
            .update(
                {
                    "leased_until": lease_until,
                    "leased_by": processor_id,
                    "attempts": OutboxMessage.attempts + 1,
                }
            )
        )
        if updated == 1:
            claimed_ids.append(message.id)

    db.session.commit()
    claimed_messages = (
        db.session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.id.in_(claimed_ids))
            .order_by(OutboxMessage.id.asc())
        )
        .scalars()
        .all()
    )
    return jsonify([message.to_dict() for message in claimed_messages])


def _lease_claim(payload: Mapping[str, object]) -> tuple[str, int | None] | str:
    """Return the caller's ``(processor_id, lease_attempt)``, or a 400 error message.

    A missing ``lease_attempt`` is returned as None: the caller has not shown that
    it holds a lease, which ``_lease_error()`` reports as a 409 conflict. A value of
    the wrong type is a malformed request (400).

    A lease is identified by the processor that holds it and the attempt number
    ``/outbox/lease`` returned for it (the message's ``attempts`` value). Settling
    requires both, so a worker whose lease expired cannot settle a newer lease,
    even one taken again under the same ``processor_id``.
    """
    processor_id = str(payload.get("processor_id", "")).strip()
    if not processor_id:
        return "processor_id is required"
    lease_attempt = payload.get("lease_attempt")
    if lease_attempt is None:
        return processor_id, None
    if isinstance(lease_attempt, bool) or not isinstance(lease_attempt, int):
        return "lease_attempt must be the integer attempts value returned by /outbox/lease"
    return processor_id, lease_attempt


def _lease_error(
    message, processor_id: str, lease_attempt: int | None, now: datetime
) -> str | None:
    """Return why the caller cannot settle ``message``, or None if it holds the lease."""
    if lease_attempt is None:
        return "lease_attempt is required: send the attempts value returned by /outbox/lease."
    if message.leased_until is None or message.leased_until <= now:
        return "Outbox message is not currently leased."
    if message.leased_by != processor_id:
        return "Outbox message is leased by a different processor."
    if message.attempts != lease_attempt:
        return "Outbox message was leased again; this lease is stale."
    return None


def _update_own_lease(
    message, processor_id: str, lease_attempt: int, now: datetime, **values: object
) -> bool:
    """Apply ``values`` only while the caller's lease is still the current one.

    The lease is checked in the UPDATE itself, against the attempt number the
    caller sent: a lease that expired and was taken again (by another processor,
    or by the same one with a new attempt number), before or after the read above,
    matches no row, so it is not overwritten.
    """
    updated = (
        db.session.query(OutboxMessage)
        .filter(
            OutboxMessage.id == message.id,
            OutboxMessage.status == "pending",
            OutboxMessage.leased_by == processor_id,
            OutboxMessage.leased_until > now,
            OutboxMessage.attempts == lease_attempt,
        )
        .update(values, synchronize_session=False)
    )
    if updated != 1:
        db.session.rollback()
        return False
    db.session.refresh(message)
    return True


@outbox_bp.post("/outbox/<int:message_id>/ack")
def acknowledge_outbox_message(message_id: int):
    payload = _json_payload()
    claim = _lease_claim(payload)
    if isinstance(claim, str):
        return jsonify({"error": claim}), 400
    processor_id, lease_attempt = claim

    message = db.session.get(OutboxMessage, message_id)
    if message is None:
        return jsonify({"error": "Outbox message not found."}), 404

    now = naive_utc_now()
    lease_error = _lease_error(message, processor_id, lease_attempt, now)
    if lease_error or lease_attempt is None:
        return jsonify({"error": lease_error}), 409

    if not _update_own_lease(
        message,
        processor_id,
        lease_attempt,
        now,
        status="sent",
        sent_at=now,
        leased_until=None,
        leased_by=None,
    ):
        return jsonify({"error": "Outbox message was leased again before this ack."}), 409

    attempt = OutboxAttempt()
    attempt.outbox_message_id = message.id
    attempt.started_at = now
    attempt.finished_at = now
    attempt.outcome = "success"
    db.session.add(attempt)

    db.session.commit()
    return jsonify(message.to_dict())


@outbox_bp.post("/outbox/<int:message_id>/fail")
def fail_outbox_message(message_id: int):
    payload = _json_payload()
    claim = _lease_claim(payload)
    if isinstance(claim, str):
        return jsonify({"error": claim}), 400
    processor_id, lease_attempt = claim

    message = db.session.get(OutboxMessage, message_id)
    if message is None:
        return jsonify({"error": "Outbox message not found."}), 404

    now = naive_utc_now()
    lease_error = _lease_error(message, processor_id, lease_attempt, now)
    if lease_error or lease_attempt is None:
        return jsonify({"error": lease_error}), 409

    error_message = str(payload.get("error", "")).strip() or "unknown error"
    # The retry decision uses the attempt number of the caller's lease; the UPDATE
    # below only applies while that lease is still the current one.
    if lease_attempt >= 3:
        outcome: dict[str, object] = {"status": "dead_letter"}
    else:
        outcome = {
            "status": "pending",
            "next_attempt_at": now + timedelta(seconds=lease_attempt * 30),
        }
    if not _update_own_lease(
        message,
        processor_id,
        lease_attempt,
        now,
        last_error=error_message,
        leased_until=None,
        leased_by=None,
        **outcome,
    ):
        return jsonify({"error": "Outbox message was leased again before this failure."}), 409

    attempt = OutboxAttempt()
    attempt.outbox_message_id = message.id
    attempt.started_at = now
    attempt.finished_at = now
    attempt.outcome = "failure"
    attempt.error_message = error_message
    db.session.add(attempt)

    db.session.commit()
    return jsonify(message.to_dict())


@outbox_bp.get("/outbox/<int:message_id>")
def get_outbox_message(message_id: int):
    message = db.session.get(OutboxMessage, message_id)
    if message is None:
        return jsonify({"error": "Outbox message not found."}), 404

    attempts = [attempt.to_dict() for attempt in message.attempts_list]
    return jsonify({**message.to_dict(), "attempts_list": attempts})


import os
from flask import Flask


def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(outbox_bp)
    return app
