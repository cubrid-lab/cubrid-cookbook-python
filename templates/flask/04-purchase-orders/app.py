# pyright: reportCallIssue=false
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

import importlib

_models = importlib.import_module("models")
PurchaseOrder = _models.PurchaseOrder
PurchaseOrderLine = _models.PurchaseOrderLine
Supplier = _models.Supplier
db = importlib.import_module("database").db

purchase_orders_bp = Blueprint("purchase_orders", __name__, url_prefix="/api")


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


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _purchase_order_or_404(order_id: int) -> PurchaseOrder:
    order = db.session.get(PurchaseOrder, order_id)
    if order is None:
        raise LookupError("Purchase order not found.")
    return order


def _invalid_transition(from_status: str, to_status: str):
    return jsonify({"error": f"Invalid transition: {from_status} -> {to_status}"}), 409


@purchase_orders_bp.post("/suppliers")
def create_supplier():
    payload = _json_payload()

    try:
        name = _required_non_empty_str(payload, "name")
        code = _required_non_empty_str(payload, "code")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    supplier = Supplier()
    supplier.name = name
    supplier.code = code
    db.session.add(supplier)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Supplier code already exists."}), 409

    return jsonify(supplier.to_dict()), 201


@purchase_orders_bp.get("/suppliers")
def list_suppliers():
    suppliers = db.session.execute(select(Supplier).order_by(Supplier.id.asc())).scalars().all()
    return jsonify([supplier.to_dict() for supplier in suppliers])


@purchase_orders_bp.post("/purchase-orders")
def create_purchase_order():
    payload = _json_payload()

    try:
        supplier_id = _required_int(payload, "supplier_id")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        return jsonify({"error": "Supplier not found."}), 404

    notes_value = payload.get("notes")
    notes = str(notes_value).strip() if isinstance(notes_value, str) else None

    lines_value = payload.get("lines", [])
    if not isinstance(lines_value, list):
        return jsonify({"error": "lines must be an array"}), 400

    order = PurchaseOrder()
    order.supplier_id = supplier_id
    order.notes = notes
    order.status = "draft"

    for index, line_value in enumerate(lines_value):
        if not isinstance(line_value, dict):
            return jsonify({"error": f"lines[{index}] must be an object"}), 400

        line_payload = cast(dict[str, object], line_value)

        try:
            sku = _required_non_empty_str(line_payload, "sku")
            description = _required_non_empty_str(line_payload, "description")
            quantity = _required_int(line_payload, "quantity")
            unit_cost = _required_int(line_payload, "unit_cost")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if quantity <= 0:
            return jsonify({"error": "quantity must be greater than zero"}), 400
        if unit_cost < 0:
            return jsonify({"error": "unit_cost cannot be negative"}), 400

        line = PurchaseOrderLine()
        line.sku = sku
        line.description = description
        line.quantity = quantity
        line.unit_cost = unit_cost
        line.received_qty = 0
        order.lines.append(line)

    db.session.add(order)
    db.session.commit()

    return jsonify({**order.to_dict(), "lines": [line.to_dict() for line in order.lines]}), 201


@purchase_orders_bp.get("/purchase-orders")
def list_purchase_orders():
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.asc())
    status = request.args.get("status")
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)

    orders = db.session.execute(stmt).scalars().all()
    return jsonify([order.to_dict() for order in orders])


@purchase_orders_bp.get("/purchase-orders/<int:order_id>")
def get_purchase_order(order_id: int):
    try:
        order = _purchase_order_or_404(order_id)
    except LookupError:
        return jsonify({"error": "Purchase order not found."}), 404

    return jsonify({**order.to_dict(), "lines": [line.to_dict() for line in order.lines]})


@purchase_orders_bp.post("/purchase-orders/<int:order_id>/submit")
def submit_purchase_order(order_id: int):
    try:
        order = _purchase_order_or_404(order_id)
    except LookupError:
        return jsonify({"error": "Purchase order not found."}), 404

    if order.status != "draft":
        return _invalid_transition(order.status, "submitted")
    if len(order.lines) == 0:
        return jsonify({"error": "Cannot submit purchase order without lines."}), 400

    result = db.session.execute(
        update(PurchaseOrder)
        .where(PurchaseOrder.id == order_id, PurchaseOrder.version == order.version)
        .values(status="submitted", submitted_at=datetime.utcnow(), version=order.version + 1)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409
    db.session.commit()

    db.session.refresh(order)
    return jsonify(order.to_dict())


@purchase_orders_bp.post("/purchase-orders/<int:order_id>/approve")
def approve_purchase_order(order_id: int):
    try:
        order = _purchase_order_or_404(order_id)
    except LookupError:
        return jsonify({"error": "Purchase order not found."}), 404

    if order.status != "submitted":
        return _invalid_transition(order.status, "approved")

    result = db.session.execute(
        update(PurchaseOrder)
        .where(PurchaseOrder.id == order_id, PurchaseOrder.version == order.version)
        .values(status="approved", approved_at=datetime.utcnow(), version=order.version + 1)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409
    db.session.commit()

    db.session.refresh(order)
    return jsonify(order.to_dict())


@purchase_orders_bp.post("/purchase-orders/<int:order_id>/receive")
def receive_purchase_order(order_id: int):
    try:
        order = _purchase_order_or_404(order_id)
    except LookupError:
        return jsonify({"error": "Purchase order not found."}), 404

    if order.status != "approved":
        return jsonify({"error": "Receive is only allowed for approved purchase orders."}), 409

    payload = _json_payload()
    lines_value = payload.get("lines")
    if not isinstance(lines_value, list):
        return jsonify({"error": "lines must be an array"}), 400

    line_by_id = {line.id: line for line in order.lines}

    for index, line_value in enumerate(lines_value):
        if not isinstance(line_value, dict):
            return jsonify({"error": f"lines[{index}] must be an object"}), 400

        line_payload = cast(dict[str, object], line_value)

        try:
            line_id = _required_int(line_payload, "line_id")
            qty_received = _required_int(line_payload, "qty_received")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if qty_received <= 0:
            return jsonify({"error": "qty_received must be greater than zero"}), 400

        line = line_by_id.get(line_id)
        if line is None:
            return jsonify({"error": "Purchase order line not found."}), 404

        next_received = line.received_qty + qty_received
        if next_received > line.quantity:
            return jsonify({"error": "Cannot receive more than ordered quantity."}), 400

        line.received_qty = next_received

    new_values: dict[str, object] = {"version": order.version + 1}
    if len(order.lines) > 0 and all(line.received_qty >= line.quantity for line in order.lines):
        new_values["status"] = "fulfilled"
        new_values["fulfilled_at"] = datetime.utcnow()

    result = db.session.execute(
        update(PurchaseOrder)
        .where(PurchaseOrder.id == order_id, PurchaseOrder.version == order.version)
        .values(**new_values)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409
    db.session.commit()

    db.session.refresh(order)
    return jsonify({**order.to_dict(), "lines": [line.to_dict() for line in order.lines]})


@purchase_orders_bp.post("/purchase-orders/<int:order_id>/cancel")
def cancel_purchase_order(order_id: int):
    try:
        order = _purchase_order_or_404(order_id)
    except LookupError:
        return jsonify({"error": "Purchase order not found."}), 404

    if order.status not in {"draft", "submitted"}:
        return _invalid_transition(order.status, "cancelled")

    result = db.session.execute(
        update(PurchaseOrder)
        .where(PurchaseOrder.id == order_id, PurchaseOrder.version == order.version)
        .values(status="cancelled", version=order.version + 1)
    )
    if cast(CursorResult[object], result).rowcount == 0:
        return jsonify({"error": "Concurrent modification detected."}), 409
    db.session.commit()

    db.session.refresh(order)
    return jsonify(order.to_dict())


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
    app.register_blueprint(purchase_orders_bp)
    return app
