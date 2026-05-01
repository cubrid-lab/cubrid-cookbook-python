from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Flask, jsonify, request
from sqlalchemy import select

from database import db
from models import Product

bp = Blueprint("basic_crud", __name__)


def _parse_price(value: str) -> Decimal:
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Price must be a valid decimal number.") from exc


def _parse_in_stock(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.lower() in {"1", "true", "yes", "on"} else 0
    return 0


@bp.get("/api/products")
def api_list_products():
    products = db.session.execute(select(Product).order_by(Product.id.desc())).scalars().all()
    return jsonify([product.to_dict() for product in products])


@bp.get("/api/products/<int:product_id>")
def api_get_product(product_id: int):
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({"error": "Product not found."}), 404
    return jsonify(product.to_dict())


@bp.post("/api/products")
def api_create_product():
    payload_value = request.get_json(silent=True)
    payload = payload_value if isinstance(payload_value, dict) else {}
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip() or None
    category = str(payload.get("category", "")).strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not category:
        return jsonify({"error": "category is required"}), 400

    try:
        price = _parse_price(str(payload.get("price", "")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    product = Product(
        name=name,
        description=description,
        price=price,
        category=category,
        in_stock=_parse_in_stock(payload.get("in_stock", 1)),
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict()), 201


@bp.put("/api/products/<int:product_id>")
def api_update_product(product_id: int):
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({"error": "Product not found."}), 404

    payload_value = request.get_json(silent=True)
    payload = payload_value if isinstance(payload_value, dict) else {}

    if "name" in payload:
        name = str(payload.get("name", "")).strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        product.name = name

    if "description" in payload:
        description = str(payload.get("description", "")).strip()
        product.description = description or None

    if "category" in payload:
        category = str(payload.get("category", "")).strip()
        if not category:
            return jsonify({"error": "category cannot be empty"}), 400
        product.category = category

    if "price" in payload:
        try:
            product.price = _parse_price(str(payload.get("price", "")))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    if "in_stock" in payload:
        product.in_stock = _parse_in_stock(payload.get("in_stock"))

    db.session.commit()
    return jsonify(product.to_dict())


@bp.delete("/api/products/<int:product_id>")
def api_delete_product(product_id: int):
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({"error": "Product not found."}), 404

    db.session.delete(product)
    db.session.commit()
    return jsonify({"message": "Product deleted successfully."}), 200


def create_app(config: dict[str, object] | None = None) -> Flask:
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
    app.register_blueprint(bp)
    return app
