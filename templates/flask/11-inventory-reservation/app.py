# pyright: reportCallIssue=false
from __future__ import annotations

import os
from typing import Any, cast
from datetime import datetime, timedelta

from flask import Blueprint, Flask, jsonify, request
from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError

from database import db  # pyright: ignore[reportImplicitRelativeImport]
from models import ExpirySweep, InventoryItem, StockReservation  # pyright: ignore[reportImplicitRelativeImport]

api = Blueprint("inventory_reservation", __name__)


def _payload() -> dict[str, object]:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return {}


def _item_view(item: InventoryItem) -> dict[str, object]:
    available = item.on_hand_qty - item.reserved_qty - item.committed_qty
    return {
        "sku": item.sku,
        "name": item.name,
        "on_hand_qty": item.on_hand_qty,
        "reserved_qty": item.reserved_qty,
        "committed_qty": item.committed_qty,
        "available_qty": available,
        "version": item.version,
    }


def _reservation_view(reservation: StockReservation) -> dict[str, object]:
    return {
        "reservation_key": reservation.reservation_key,
        "item_id": reservation.item_id,
        "client_id": reservation.client_id,
        "quantity": reservation.quantity,
        "state": reservation.state,
        "expires_at": reservation.expires_at.isoformat(),
        "confirmed_at": reservation.confirmed_at.isoformat() if reservation.confirmed_at else None,
        "released_at": reservation.released_at.isoformat() if reservation.released_at else None,
        "version": reservation.version,
    }


@api.post("/items")
def create_item():
    payload = _payload()
    sku = str(payload.get("sku", "")).strip()
    name = str(payload.get("name", "")).strip()
    on_hand_qty = payload.get("on_hand_qty")

    if not sku or not name:
        return jsonify({"error": "sku and name are required"}), 400
    if isinstance(on_hand_qty, bool) or not isinstance(on_hand_qty, int) or on_hand_qty < 0:
        return jsonify({"error": "on_hand_qty must be a non-negative integer"}), 400

    item = InventoryItem()
    item.sku = sku
    item.name = name
    item.on_hand_qty = on_hand_qty
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "sku already exists"}), 409

    return jsonify(_item_view(item)), 201


@api.get("/items/<string:sku>")
def get_item(sku: str):
    item = db.session.execute(
        select(InventoryItem).where(InventoryItem.sku == sku)
    ).scalar_one_or_none()
    if item is None:
        return jsonify({"error": "item not found"}), 404
    return jsonify(_item_view(item))


@api.post("/reservations")
def create_reservation():
    payload = _payload()
    reservation_key = str(payload.get("reservation_key", "")).strip()
    sku = str(payload.get("sku", "")).strip()
    client_id = str(payload.get("client_id", "")).strip()
    quantity = payload.get("quantity")
    ttl_seconds = payload.get("ttl_seconds")

    if not reservation_key or not sku or not client_id:
        return jsonify({"error": "reservation_key, sku, and client_id are required"}), 400
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity must be a positive integer"}), 400
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        return jsonify({"error": "ttl_seconds must be a positive integer"}), 400

    item = db.session.execute(
        select(InventoryItem).where(InventoryItem.sku == sku)
    ).scalar_one_or_none()
    if item is None:
        return jsonify({"error": "item not found"}), 404

    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)

    updated = db.session.execute(
        update(InventoryItem)
        .where(
            and_(
                InventoryItem.id == item.id,
                InventoryItem.version == item.version,
                (
                    InventoryItem.on_hand_qty
                    - InventoryItem.reserved_qty
                    - InventoryItem.committed_qty
                )
                >= quantity,
            )
        )
        .values(
            reserved_qty=InventoryItem.reserved_qty + quantity,
            version=InventoryItem.version + 1,
        )
    )

    if getattr(updated, "rowcount", 0) != 1:
        db.session.rollback()
        fresh = db.session.execute(
            select(InventoryItem).where(InventoryItem.id == item.id)
        ).scalar_one_or_none()
        if fresh is None:
            return jsonify({"error": "item not found"}), 404
        available = fresh.on_hand_qty - fresh.reserved_qty - fresh.committed_qty
        if available < quantity:
            return jsonify({"error": "insufficient stock"}), 422
        return jsonify({"error": "concurrent update conflict"}), 409

    reservation = StockReservation()
    reservation.reservation_key = reservation_key
    reservation.item_id = item.id
    reservation.client_id = client_id
    reservation.quantity = quantity
    reservation.state = "active"
    reservation.expires_at = expires_at
    db.session.add(reservation)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "reservation key already exists"}), 409

    return jsonify(_reservation_view(reservation)), 201


@api.get("/reservations/<string:reservation_key>")
def get_reservation(reservation_key: str):
    reservation = db.session.execute(
        select(StockReservation).where(StockReservation.reservation_key == reservation_key)
    ).scalar_one_or_none()
    if reservation is None:
        return jsonify({"error": "reservation not found"}), 404
    return jsonify(_reservation_view(reservation))


@api.post("/reservations/<string:reservation_key>/confirm")
def confirm_reservation(reservation_key: str):
    reservation = db.session.execute(
        select(StockReservation).where(StockReservation.reservation_key == reservation_key)
    ).scalar_one_or_none()
    if reservation is None:
        return jsonify({"error": "reservation not found"}), 404

    now = datetime.utcnow()
    if reservation.state != "active":
        return jsonify({"error": "reservation is not active"}), 409
    if reservation.expires_at <= now:
        return jsonify({"error": "reservation expired"}), 422

    reservation_update = db.session.execute(
        update(StockReservation)
        .where(
            and_(
                StockReservation.id == reservation.id,
                StockReservation.version == reservation.version,
                StockReservation.state == "active",
                StockReservation.expires_at > now,
            )
        )
        .values(
            state="confirmed",
            confirmed_at=now,
            version=StockReservation.version + 1,
        )
    )
    if getattr(reservation_update, "rowcount", 0) != 1:
        db.session.rollback()
        return jsonify({"error": "stale reservation state"}), 409

    item_update = db.session.execute(
        update(InventoryItem)
        .where(
            and_(
                InventoryItem.id == reservation.item_id,
                InventoryItem.reserved_qty >= reservation.quantity,
            )
        )
        .values(
            reserved_qty=InventoryItem.reserved_qty - reservation.quantity,
            committed_qty=InventoryItem.committed_qty + reservation.quantity,
            version=InventoryItem.version + 1,
        )
    )
    if getattr(item_update, "rowcount", 0) != 1:
        db.session.rollback()
        return jsonify({"error": "stale inventory state"}), 409

    db.session.commit()
    confirmed = db.session.execute(
        select(StockReservation).where(StockReservation.id == reservation.id)
    ).scalar_one()
    return jsonify(_reservation_view(confirmed))


@api.post("/reservations/<string:reservation_key>/cancel")
def cancel_reservation(reservation_key: str):
    reservation = db.session.execute(
        select(StockReservation).where(StockReservation.reservation_key == reservation_key)
    ).scalar_one_or_none()
    if reservation is None:
        return jsonify({"error": "reservation not found"}), 404
    if reservation.state != "active":
        return jsonify({"error": "reservation is not active"}), 409

    now = datetime.utcnow()
    reservation_update = db.session.execute(
        update(StockReservation)
        .where(
            and_(
                StockReservation.id == reservation.id,
                StockReservation.version == reservation.version,
                StockReservation.state == "active",
            )
        )
        .values(
            state="cancelled",
            released_at=now,
            version=StockReservation.version + 1,
        )
    )
    if getattr(reservation_update, "rowcount", 0) != 1:
        db.session.rollback()
        return jsonify({"error": "stale reservation state"}), 409

    item_update = db.session.execute(
        update(InventoryItem)
        .where(
            and_(
                InventoryItem.id == reservation.item_id,
                InventoryItem.reserved_qty >= reservation.quantity,
            )
        )
        .values(
            reserved_qty=InventoryItem.reserved_qty - reservation.quantity,
            version=InventoryItem.version + 1,
        )
    )
    if getattr(item_update, "rowcount", 0) != 1:
        db.session.rollback()
        return jsonify({"error": "stale inventory state"}), 409

    db.session.commit()
    cancelled = db.session.execute(
        select(StockReservation).where(StockReservation.id == reservation.id)
    ).scalar_one()
    return jsonify(_reservation_view(cancelled))


@api.post("/sweeps/expire")
def expire_reservations():
    now = datetime.utcnow()
    sweep = ExpirySweep()
    sweep.started_at = now
    sweep.status = "running"
    db.session.add(sweep)
    db.session.flush()

    stale = db.session.execute(
        select(StockReservation)
        .where(
            and_(
                StockReservation.state == "active",
                StockReservation.expires_at <= now,
            )
        )
        .order_by(StockReservation.id.asc())
    ).scalars()

    expired_count = 0
    failed_count = 0

    for reservation in stale:
        try:
            with db.session.begin_nested():
                reservation_update = db.session.execute(
                    update(StockReservation)
                    .where(
                        and_(
                            StockReservation.id == reservation.id,
                            StockReservation.version == reservation.version,
                            StockReservation.state == "active",
                            StockReservation.expires_at <= now,
                        )
                    )
                    .values(
                        state="expired",
                        released_at=now,
                        version=StockReservation.version + 1,
                    )
                )
                if getattr(reservation_update, "rowcount", 0) != 1:
                    raise ValueError("reservation became stale")

                item_update = db.session.execute(
                    update(InventoryItem)
                    .where(
                        and_(
                            InventoryItem.id == reservation.item_id,
                            InventoryItem.reserved_qty >= reservation.quantity,
                        )
                    )
                    .values(
                        reserved_qty=InventoryItem.reserved_qty - reservation.quantity,
                        version=InventoryItem.version + 1,
                    )
                )
                if getattr(item_update, "rowcount", 0) != 1:
                    raise ValueError("failed to release inventory")

            expired_count += 1
        except Exception:
            failed_count += 1

    sweep.finished_at = datetime.utcnow()
    sweep.status = "completed" if failed_count == 0 else "completed_with_errors"
    sweep.expired_count = expired_count
    if failed_count > 0:
        sweep.error_text = f"{failed_count} reservations failed during expiry"

    db.session.commit()
    return jsonify(
        {"expired_count": expired_count, "failed_count": failed_count, "sweep_id": sweep.id}
    )


def create_app(config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "cubrid+pycubrid://dba@localhost:33000/testdb"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(cast(dict[str, Any], config))

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.register_blueprint(api)
    return app
