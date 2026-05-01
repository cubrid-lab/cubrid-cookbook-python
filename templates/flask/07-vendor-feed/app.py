# pyright: reportCallIssue=false
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import importlib

_models = importlib.import_module("models")
CatalogProduct = _models.CatalogProduct
ImportBatch = _models.ImportBatch
ImportRow = _models.ImportRow
Product = _models.Product
db = importlib.import_module("database").db

imports_bp = Blueprint("imports", __name__, url_prefix="/api")


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


def _import_batch_or_404(batch_id: int) -> ImportBatch:
    batch = db.session.get(ImportBatch, batch_id)
    if batch is None:
        raise LookupError("Import batch not found.")
    return batch


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validation_error(row: ImportRow) -> tuple[str, str] | None:
    if not row.external_sku.strip():
        return ("missing_external_sku", "external_sku is required")
    if row.name is None or not row.name.strip():
        return ("missing_name", "name is required")
    if row.price_cents is None or not _is_positive_int(row.price_cents):
        return ("invalid_price_cents", "price_cents must be greater than zero")
    return None


@imports_bp.post("/imports")
def create_import_batch():
    payload = _json_payload()
    try:
        vendor_name = _required_non_empty_str(payload, "vendor_name")
        source_filename = _required_non_empty_str(payload, "source_filename")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    batch = ImportBatch()
    batch.vendor_name = vendor_name
    batch.source_filename = source_filename
    batch.status = "uploaded"
    db.session.add(batch)
    db.session.commit()
    return jsonify(batch.to_dict()), 201


@imports_bp.get("/imports")
def list_import_batches():
    batches = db.session.execute(select(ImportBatch).order_by(ImportBatch.id.asc())).scalars().all()
    return jsonify([batch.to_dict() for batch in batches])


@imports_bp.get("/imports/<int:batch_id>")
def get_import_batch(batch_id: int):
    try:
        batch = _import_batch_or_404(batch_id)
    except LookupError:
        return jsonify({"error": "Import batch not found."}), 404

    rows = (
        db.session.execute(
            select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_no.asc())
        )
        .scalars()
        .all()
    )
    return jsonify({**batch.to_dict(), "rows": [row.to_dict() for row in rows]})


@imports_bp.post("/imports/<int:batch_id>/rows")
def add_import_rows(batch_id: int):
    try:
        batch = _import_batch_or_404(batch_id)
    except LookupError:
        return jsonify({"error": "Import batch not found."}), 404

    if batch.status != "uploaded":
        return jsonify({"error": "Rows can only be added when batch status is uploaded."}), 409

    payload = _json_payload()
    rows_value = payload.get("rows")
    if not isinstance(rows_value, Sequence) or isinstance(rows_value, str):
        return jsonify({"error": "rows must be an array"}), 400

    rows_to_add: list[ImportRow] = []
    for index, row_value in enumerate(rows_value):
        if not isinstance(row_value, Mapping):
            return jsonify({"error": f"rows[{index}] must be an object"}), 400

        row_payload = cast(dict[str, object], row_value)

        row_no = row_payload.get("row_no")
        price_cents = row_payload.get("price_cents")
        if not isinstance(row_no, int) or isinstance(row_no, bool):
            return jsonify({"error": f"rows[{index}].row_no must be an integer"}), 400
        if price_cents is not None and (
            not isinstance(price_cents, int) or isinstance(price_cents, bool)
        ):
            return jsonify({"error": f"rows[{index}].price_cents must be an integer"}), 400

        row = ImportRow()
        row.batch_id = batch.id
        row.row_no = row_no
        row.external_sku = str(row_payload.get("external_sku", "")).strip()
        name_value = row_payload.get("name")
        row.name = str(name_value).strip() if isinstance(name_value, str) else None
        row.price_cents = price_cents
        row.raw_payload = str(row_payload.get("raw_payload", ""))
        row.validation_status = "pending"
        row.error_code = None
        row.error_message = None
        row.promoted_product_id = None
        rows_to_add.append(row)

    db.session.add_all(rows_to_add)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Duplicate row_no within batch."}), 409

    return jsonify({"batch_id": batch.id, "count": len(rows_to_add)}), 201


@imports_bp.post("/imports/<int:batch_id>/validate")
def validate_import_batch(batch_id: int):
    try:
        batch = _import_batch_or_404(batch_id)
    except LookupError:
        return jsonify({"error": "Import batch not found."}), 404

    if batch.status != "uploaded":
        return jsonify({"error": "Validation is only allowed when batch status is uploaded."}), 409

    rows = (
        db.session.execute(
            select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_no.asc())
        )
        .scalars()
        .all()
    )

    valid_count = 0
    invalid_count = 0
    for row in rows:
        error = _validation_error(row)
        if error is None:
            row.validation_status = "valid"
            row.error_code = None
            row.error_message = None
            valid_count += 1
            continue

        row.validation_status = "invalid"
        row.error_code = error[0]
        row.error_message = error[1]
        invalid_count += 1

    batch.status = "validated"
    batch.validated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(
        {
            "batch_id": batch.id,
            "status": batch.status,
            "total_rows": len(rows),
            "valid_rows": valid_count,
            "invalid_rows": invalid_count,
        }
    )


@imports_bp.post("/imports/<int:batch_id>/promote")
def promote_import_batch(batch_id: int):
    try:
        batch = _import_batch_or_404(batch_id)
    except LookupError:
        return jsonify({"error": "Import batch not found."}), 404

    if batch.status == "promoted":
        return jsonify({"error": "Batch already promoted."}), 409
    if batch.status != "validated":
        return jsonify({"error": "Promotion is only allowed when batch status is validated."}), 409

    transition_updated = (
        db.session.query(ImportBatch)
        .filter(ImportBatch.id == batch.id, ImportBatch.status == "validated")
        .update({"status": "promoting"})
    )
    if transition_updated == 0:
        db.session.rollback()
        return jsonify({"error": "Promotion is only allowed when batch status is validated."}), 409

    rows = (
        db.session.execute(
            select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_no.asc())
        )
        .scalars()
        .all()
    )

    promoted_count = 0
    skipped_count = 0
    for row in rows:
        if row.validation_status != "valid":
            skipped_count += 1
            continue

        savepoint = db.session.begin_nested()
        try:
            product = db.session.execute(
                select(CatalogProduct).where(
                    CatalogProduct.vendor_name == batch.vendor_name,
                    CatalogProduct.external_sku == row.external_sku,
                )
            ).scalar_one_or_none()

            if product is None:
                product = CatalogProduct()
                product.vendor_name = batch.vendor_name
                product.external_sku = row.external_sku
                db.session.add(product)

            product.name = row.name or ""
            product.price_cents = cast(int, row.price_cents)
            product.active = 1
            db.session.flush()

            row.promoted_product_id = product.id
            savepoint.commit()
            promoted_count += 1
        except IntegrityError:
            savepoint.rollback()
            skipped_count += 1

    batch.status = "promoted"
    batch.promoted_at = datetime.utcnow()
    db.session.commit()

    return jsonify(
        {
            "batch_id": batch.id,
            "status": batch.status,
            "promoted_rows": promoted_count,
            "skipped_rows": skipped_count,
        }
    )


@imports_bp.get("/products")
def list_catalog_products():
    vendor_name = request.args.get("vendor_name")
    if vendor_name is None:
        products = db.session.execute(select(Product).order_by(Product.id.desc())).scalars().all()
        return jsonify([product.to_dict() for product in products])

    stmt = select(CatalogProduct).where(CatalogProduct.vendor_name == vendor_name)
    products = db.session.execute(stmt.order_by(CatalogProduct.id.asc())).scalars().all()
    return jsonify([product.to_dict() for product in products])


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
    app.register_blueprint(imports_bp)
    return app
