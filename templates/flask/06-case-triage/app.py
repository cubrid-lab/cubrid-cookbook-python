# pyright: reportCallIssue=false
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, or_, select

import importlib

_models = importlib.import_module("models")
ReviewCase = _models.ReviewCase
ReviewNote = _models.ReviewNote
db = importlib.import_module("database").db

cases_bp = Blueprint("cases", __name__, url_prefix="/api")


def _json_payload() -> Mapping[str, object]:
    payload_value = request.get_json(silent=True)
    if isinstance(payload_value, dict):
        return cast(dict[str, object], payload_value)
    return {}


def _required_non_empty_str(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_int(payload: Mapping[str, object], key: str, default: int = 0) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _case_or_404(case_id: int) -> ReviewCase:
    review_case = db.session.get(ReviewCase, case_id)
    if review_case is None:
        raise LookupError("Case not found.")
    return review_case


def _claim_case(
    review_case: ReviewCase, agent: str, now: datetime
) -> tuple[dict[str, object], int] | None:
    if review_case.status == "new":
        pass
    elif (
        review_case.status == "claimed"
        and review_case.lease_expires_at is not None
        and review_case.lease_expires_at < now
    ):
        pass
    else:
        return {"error": "Case already claimed and lease not expired."}, 409

    updated = (
        db.session.query(ReviewCase)
        .filter(
            ReviewCase.id == review_case.id,
            ReviewCase.version == review_case.version,
        )
        .update(
            {
                "claimed_by": agent,
                "lease_expires_at": now + timedelta(minutes=15),
                "status": "claimed",
                "version": review_case.version + 1,
            }
        )
    )
    if updated == 0:
        return {"error": "Concurrent modification detected."}, 409

    db.session.commit()
    db.session.refresh(review_case)
    return None


@cases_bp.post("/cases")
def create_case():
    payload = _json_payload()

    try:
        customer_email = _required_non_empty_str(payload, "customer_email")
        subject = _required_non_empty_str(payload, "subject")
        body = _required_non_empty_str(payload, "body")
        priority = _optional_int(payload, "priority", default=0)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    review_case = ReviewCase()
    review_case.customer_email = customer_email
    review_case.subject = subject
    review_case.body = body
    review_case.priority = priority
    review_case.status = "new"

    db.session.add(review_case)
    db.session.commit()
    return jsonify(review_case.to_dict()), 201


@cases_bp.get("/cases")
def list_cases():
    stmt = select(ReviewCase).order_by(ReviewCase.priority.desc(), ReviewCase.created_at.asc())
    status = request.args.get("status")
    if status is not None:
        stmt = stmt.where(ReviewCase.status == status)

    review_cases = db.session.execute(stmt).scalars().all()
    return jsonify([review_case.to_dict() for review_case in review_cases])


@cases_bp.get("/cases/<int:case_id>")
def get_case(case_id: int):
    try:
        review_case = _case_or_404(case_id)
    except LookupError:
        return jsonify({"error": "Case not found."}), 404

    notes = sorted(review_case.notes, key=lambda note: note.created_at)
    return jsonify({**review_case.to_dict(), "notes": [note.to_dict() for note in notes]})


@cases_bp.post("/cases/<int:case_id>/claim")
def claim_case(case_id: int):
    payload = _json_payload()
    try:
        agent = _required_non_empty_str(payload, "agent")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        review_case = _case_or_404(case_id)
    except LookupError:
        return jsonify({"error": "Case not found."}), 404

    claim_error = _claim_case(review_case, agent, datetime.utcnow())
    if claim_error is not None:
        return jsonify(claim_error[0]), claim_error[1]
    return jsonify(review_case.to_dict())


@cases_bp.post("/cases/<int:case_id>/release")
def release_case(case_id: int):
    payload = _json_payload()
    try:
        agent = _required_non_empty_str(payload, "agent")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        review_case = _case_or_404(case_id)
    except LookupError:
        return jsonify({"error": "Case not found."}), 404

    if review_case.status != "claimed" or review_case.claimed_by != agent:
        return jsonify({"error": "Case can only be released by current claimant."}), 409

    updated = (
        db.session.query(ReviewCase)
        .filter(
            ReviewCase.id == review_case.id,
            ReviewCase.version == review_case.version,
        )
        .update(
            {
                "status": "new",
                "claimed_by": None,
                "lease_expires_at": None,
                "version": review_case.version + 1,
            }
        )
    )
    if updated == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409

    db.session.commit()
    db.session.refresh(review_case)
    return jsonify(review_case.to_dict())


@cases_bp.post("/cases/<int:case_id>/resolve")
def resolve_case(case_id: int):
    payload = _json_payload()
    try:
        agent = _required_non_empty_str(payload, "agent")
        resolution_note = _required_non_empty_str(payload, "resolution_note")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        review_case = _case_or_404(case_id)
    except LookupError:
        return jsonify({"error": "Case not found."}), 404

    now = datetime.utcnow()
    if review_case.status != "claimed" or review_case.claimed_by != agent:
        return jsonify({"error": "Case can only be resolved by current claimant."}), 409
    if review_case.lease_expires_at is None or review_case.lease_expires_at <= now:
        return jsonify({"error": "Cannot resolve case with expired lease."}), 409

    updated = (
        db.session.query(ReviewCase)
        .filter(
            ReviewCase.id == review_case.id,
            ReviewCase.version == review_case.version,
        )
        .update(
            {
                "status": "resolved",
                "resolved_at": now,
                "claimed_by": None,
                "lease_expires_at": None,
                "version": review_case.version + 1,
            }
        )
    )
    if updated == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409

    note = ReviewNote()
    note.case_id = review_case.id
    note.author = agent
    note.body = resolution_note
    db.session.add(note)
    db.session.commit()

    db.session.refresh(review_case)
    return jsonify(review_case.to_dict())


@cases_bp.post("/cases/claim-next")
def claim_next_case():
    payload = _json_payload()
    try:
        agent = _required_non_empty_str(payload, "agent")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    for _ in range(2):
        now = datetime.utcnow()
        next_case = db.session.execute(
            select(ReviewCase)
            .where(
                or_(
                    and_(ReviewCase.status == "new", ReviewCase.claimed_by.is_(None)),
                    and_(ReviewCase.status == "claimed", ReviewCase.lease_expires_at < now),
                )
            )
            .order_by(ReviewCase.priority.desc(), ReviewCase.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()

        if next_case is None:
            return jsonify({"error": "No claimable case found."}), 404

        updated = (
            db.session.query(ReviewCase)
            .filter(
                ReviewCase.id == next_case.id,
                or_(
                    and_(ReviewCase.status == "new", ReviewCase.claimed_by.is_(None)),
                    and_(ReviewCase.status == "claimed", ReviewCase.lease_expires_at < now),
                ),
            )
            .update(
                {
                    "claimed_by": agent,
                    "lease_expires_at": now + timedelta(minutes=15),
                    "status": "claimed",
                    "version": ReviewCase.version + 1,
                }
            )
        )
        if updated == 1:
            db.session.commit()
            claimed_case = db.session.get(ReviewCase, next_case.id)
            if claimed_case is None:
                return jsonify({"error": "No claimable case found."}), 404
            return jsonify(claimed_case.to_dict())

    db.session.rollback()
    return jsonify({"error": "No claimable case found."}), 404


@cases_bp.post("/cases/<int:case_id>/notes")
def add_case_note(case_id: int):
    payload = _json_payload()
    try:
        author = _required_non_empty_str(payload, "author")
        body = _required_non_empty_str(payload, "body")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        review_case = _case_or_404(case_id)
    except LookupError:
        return jsonify({"error": "Case not found."}), 404

    note = ReviewNote()
    note.case_id = review_case.id
    note.author = author
    note.body = body

    db.session.add(note)
    db.session.commit()
    return jsonify(note.to_dict()), 201


import os
from flask import Flask

def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(cases_bp)
    return app
