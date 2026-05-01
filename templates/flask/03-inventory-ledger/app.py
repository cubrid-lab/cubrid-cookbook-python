# pyright: reportCallIssue=false
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy.engine import CursorResult
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import importlib

_models = importlib.import_module("models")
StockItem = _models.StockItem
StockMovement = _models.StockMovement
Warehouse = _models.Warehouse
db = importlib.import_module("database").db

inventory_bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")


def _json_payload() -> Mapping[str, object]:
    payload_value = request.get_json(silent=True)
    if isinstance(payload_value, dict):
        return cast(dict[str, object], payload_value)
    return {}


def _int_field(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


@inventory_bp.post("/warehouses")
def create_warehouse():
    payload = _json_payload()
    code = str(payload.get("code", "")).strip()
    name = str(payload.get("name", "")).strip()

    if not code:
        return jsonify({"error": "code is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400

    warehouse = Warehouse()
    warehouse.code = code
    warehouse.name = name
    db.session.add(warehouse)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Warehouse code already exists."}), 409
    return jsonify(warehouse.to_dict()), 201


@inventory_bp.get("/warehouses")
def list_warehouses():
    warehouses = db.session.execute(select(Warehouse).order_by(Warehouse.id.asc())).scalars().all()
    return jsonify([warehouse.to_dict() for warehouse in warehouses])


@inventory_bp.post("/items")
def create_stock_item():
    payload = _json_payload()

    try:
        warehouse_id = _int_field(payload, "warehouse_id")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    sku = str(payload.get("sku", "")).strip()
    product_name = str(payload.get("product_name", "")).strip()

    if not sku:
        return jsonify({"error": "sku is required"}), 400
    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    on_hand_qty = payload.get("on_hand_qty", 0)
    if isinstance(on_hand_qty, bool) or not isinstance(on_hand_qty, int):
        return jsonify({"error": "on_hand_qty must be an integer"}), 400
    if on_hand_qty < 0:
        return jsonify({"error": "on_hand_qty cannot be negative"}), 400

    warehouse = db.session.get(Warehouse, warehouse_id)
    if warehouse is None:
        return jsonify({"error": "Warehouse not found."}), 404

    item = StockItem()
    item.warehouse_id = warehouse_id
    item.sku = sku
    item.product_name = product_name
    item.on_hand_qty = on_hand_qty
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Item with this SKU already exists in this warehouse."}), 409
    return jsonify(item.to_dict()), 201


@inventory_bp.get("/items")
def list_stock_items():
    stmt = select(StockItem).order_by(StockItem.id.asc())
    warehouse_id_param = request.args.get("warehouse_id")
    if warehouse_id_param is not None:
        try:
            warehouse_id = int(warehouse_id_param)
        except (TypeError, ValueError):
            return jsonify({"error": "warehouse_id must be an integer"}), 400
        stmt = stmt.where(StockItem.warehouse_id == warehouse_id)

    items = db.session.execute(stmt).scalars().all()
    return jsonify([item.to_dict() for item in items])


@inventory_bp.get("/items/<int:item_id>")
def get_stock_item(item_id: int):
    item = db.session.get(StockItem, item_id)
    if item is None:
        return jsonify({"error": "Stock item not found."}), 404

    recent_movements = (
        db.session.execute(
            select(StockMovement)
            .where(StockMovement.stock_item_id == item.id)
            .order_by(StockMovement.id.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    return jsonify(
        {
            **item.to_dict(),
            "movements": [movement.to_dict() for movement in recent_movements],
        }
    )


@inventory_bp.post("/adjustments")
def adjust_stock():
    payload = _json_payload()

    try:
        stock_item_id = _int_field(payload, "stock_item_id")
        qty_delta = _int_field(payload, "qty_delta")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    item = db.session.get(StockItem, stock_item_id)
    if item is None:
        return jsonify({"error": "Stock item not found."}), 404

    resulting_qty = item.on_hand_qty + qty_delta
    if resulting_qty < 0:
        db.session.rollback()
        return jsonify({"error": "Insufficient stock for adjustment."}), 409

    note_value = payload.get("note")
    note = str(note_value).strip() if isinstance(note_value, str) else None

    try:
        # Optimistic locking: conditional update on version
        current_version = item.version
        result = db.session.execute(
            update(StockItem)
            .where(StockItem.id == item.id, StockItem.version == current_version)
            .values(on_hand_qty=resulting_qty, version=current_version + 1)
        )
        if cast(CursorResult[object], result).rowcount == 0:
            db.session.rollback()
            return jsonify({"error": "Concurrent modification, please retry."}), 409

        movement = StockMovement()
        movement.stock_item_id = item.id
        movement.movement_type = "adjustment"
        movement.qty_delta = qty_delta
        movement.note = note
        db.session.add(movement)
        db.session.commit()
        db.session.refresh(item)
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Unable to adjust stock."}), 500
    return jsonify({"item": item.to_dict(), "movement": movement.to_dict()})


@inventory_bp.post("/transfers")
def transfer_stock():
    payload = _json_payload()

    try:
        from_item_id = _int_field(payload, "from_item_id")
        to_item_id = _int_field(payload, "to_item_id")
        quantity = _int_field(payload, "quantity")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if quantity <= 0:
        return jsonify({"error": "quantity must be greater than zero"}), 400
    if from_item_id == to_item_id:
        return jsonify({"error": "from_item_id and to_item_id must be different"}), 400

    from_item = db.session.get(StockItem, from_item_id)
    to_item = db.session.get(StockItem, to_item_id)
    if from_item is None or to_item is None:
        return jsonify({"error": "Stock item not found."}), 404

    if from_item.sku != to_item.sku:
        return jsonify({"error": "Cannot transfer between items with different SKUs."}), 400
    if from_item.on_hand_qty < quantity:
        db.session.rollback()
        return jsonify({"error": "Insufficient stock for transfer."}), 409

    note_value = payload.get("note")
    note = str(note_value).strip() if isinstance(note_value, str) else None
    reference = f"transfer:{from_item.id}->{to_item.id}"

    try:
        # Optimistic locking on source
        from_version = from_item.version
        result = db.session.execute(
            update(StockItem)
            .where(StockItem.id == from_item.id, StockItem.version == from_version)
            .values(on_hand_qty=from_item.on_hand_qty - quantity, version=from_version + 1)
        )
        if cast(CursorResult[object], result).rowcount == 0:
            db.session.rollback()
            return jsonify({"error": "Concurrent modification, please retry."}), 409

        # Update destination with version bump
        to_version = to_item.version
        result_to = db.session.execute(
            update(StockItem)
            .where(StockItem.id == to_item.id, StockItem.version == to_version)
            .values(on_hand_qty=to_item.on_hand_qty + quantity, version=to_version + 1)
        )
        if cast(CursorResult[object], result_to).rowcount == 0:
            db.session.rollback()
            return jsonify({"error": "Concurrent modification, please retry."}), 409

        out_movement = StockMovement()
        out_movement.stock_item_id = from_item.id
        out_movement.movement_type = "transfer_out"
        out_movement.qty_delta = -quantity
        out_movement.reference = reference
        out_movement.note = note

        in_movement = StockMovement()
        in_movement.stock_item_id = to_item.id
        in_movement.movement_type = "transfer_in"
        in_movement.qty_delta = quantity
        in_movement.reference = reference
        in_movement.note = note

        db.session.add(out_movement)
        db.session.add(in_movement)
        db.session.commit()
        db.session.refresh(from_item)
        db.session.refresh(to_item)
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Unable to complete transfer."}), 500

    return jsonify(
        {
            "from_item": from_item.to_dict(),
            "to_item": to_item.to_dict(),
            "movements": [out_movement.to_dict(), in_movement.to_dict()],
        }
    )


@inventory_bp.get("/items/<int:item_id>/movements")
def list_stock_item_movements(item_id: int):
    item = db.session.get(StockItem, item_id)
    if item is None:
        return jsonify({"error": "Stock item not found."}), 404

    movements = (
        db.session.execute(
            select(StockMovement)
            .where(StockMovement.stock_item_id == item.id)
            .order_by(StockMovement.id.desc())
        )
        .scalars()
        .all()
    )
    return jsonify([movement.to_dict() for movement in movements])


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
    app.register_blueprint(inventory_bp)
    return app
