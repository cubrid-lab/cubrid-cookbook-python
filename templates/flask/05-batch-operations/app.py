# pyright: reportCallIssue=false
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import importlib

_models = importlib.import_module("models")
BatchJob = _models.BatchJob
BatchJobRow = _models.BatchJobRow
BatchProduct = _models.BatchProduct
db = importlib.import_module("database").db

batch_bp = Blueprint("batch", __name__, url_prefix="/api/batch")


def _json_payload() -> Mapping[str, object]:
    payload_value = request.get_json(silent=True)
    if isinstance(payload_value, dict):
        return cast(dict[str, object], payload_value)
    return {}


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@batch_bp.post("/products")
def create_batch_product():
    payload = _json_payload()
    sku = str(payload.get("sku", "")).strip()
    name = str(payload.get("name", "")).strip()
    price = payload.get("price")

    if not sku:
        return jsonify({"error": "sku is required"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not _is_positive_int(price):
        return jsonify({"error": "price must be a positive integer"}), 400

    product = BatchProduct()
    product.sku = sku
    product.name = name
    product.price = cast(int, price)
    db.session.add(product)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "sku already exists"}), 409
    return jsonify(product.to_dict()), 201


@batch_bp.get("/products")
def list_batch_products():
    products = (
        db.session.execute(select(BatchProduct).order_by(BatchProduct.id.asc())).scalars().all()
    )
    return jsonify([product.to_dict() for product in products])


@batch_bp.post("/products/seed")
def seed_batch_products():
    payload = _json_payload()
    products_value = payload.get("products")
    if not isinstance(products_value, Sequence) or isinstance(products_value, str):
        return jsonify({"error": "products must be an array"}), 400

    created_products: list[BatchProduct] = []
    for item in products_value:
        if not isinstance(item, Mapping):
            return jsonify({"error": "each product must be an object"}), 400

        sku = str(item.get("sku", "")).strip()
        name = str(item.get("name", "")).strip()
        price = item.get("price")

        if not sku:
            return jsonify({"error": "sku is required"}), 400
        if not name:
            return jsonify({"error": "name is required"}), 400
        if not _is_positive_int(price):
            return jsonify({"error": "price must be a positive integer"}), 400

        product = BatchProduct()
        product.sku = sku
        product.name = name
        product.price = cast(int, price)
        created_products.append(product)

    db.session.add_all(created_products)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "One or more skus already exist"}), 409

    return jsonify({"count": len(created_products)}), 201


@batch_bp.post("/jobs/price-update")
def submit_price_update_job():
    payload = _json_payload()
    updates_value = payload.get("updates")
    if not isinstance(updates_value, Sequence) or isinstance(updates_value, str):
        return jsonify({"error": "updates must be an array"}), 400
    if len(updates_value) == 0:
        return jsonify({"error": "updates cannot be empty"}), 400

    job = BatchJob()
    job.job_type = "price_update"
    job.total_rows = len(updates_value)
    db.session.add(job)
    db.session.flush()

    success_cnt = 0
    failed_cnt = 0
    errors: list[dict[str, object]] = []

    for row_index, item in enumerate(updates_value, start=1):
        row = BatchJobRow()
        row.job_id = job.id
        row.row_index = row_index

        if not isinstance(item, Mapping):
            row.sku = ""
            row.payload = json.dumps({})
            row.status = "failed"
            row.error_message = "Row must be an object"
            failed_cnt += 1
            errors.append({"row_index": row_index, "sku": "", "error": row.error_message})
            db.session.add(row)
            continue

        sku = str(item.get("sku", "")).strip()
        new_price = item.get("new_price")

        row.sku = sku
        row.payload = json.dumps({"sku": sku, "new_price": new_price})

        if not sku:
            row.status = "failed"
            row.error_message = "SKU is required"
            failed_cnt += 1
            errors.append({"row_index": row_index, "sku": sku, "error": row.error_message})
            db.session.add(row)
            continue

        if not _is_positive_int(new_price):
            row.status = "failed"
            row.error_message = "new_price must be a positive integer"
            failed_cnt += 1
            errors.append({"row_index": row_index, "sku": sku, "error": row.error_message})
            db.session.add(row)
            continue

        product = db.session.execute(
            select(BatchProduct).where(BatchProduct.sku == sku)
        ).scalar_one_or_none()
        if product is None:
            row.status = "failed"
            row.error_message = "SKU not found"
            failed_cnt += 1
            errors.append({"row_index": row_index, "sku": sku, "error": row.error_message})
            db.session.add(row)
            continue

        product.price = cast(int, new_price)
        row.status = "success"
        row.error_message = None
        success_cnt += 1
        db.session.add(row)

    job.success_cnt = success_cnt
    job.failed_cnt = failed_cnt
    job.status = "completed"
    job.finished_at = datetime.utcnow()

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Database error during batch processing"}), 500
    return jsonify(
        {
            "job_id": job.id,
            "status": job.status,
            "total_rows": job.total_rows,
            "success_cnt": job.success_cnt,
            "failed_cnt": job.failed_cnt,
            "errors": errors,
        }
    ), 201

@batch_bp.get("/jobs")
def list_batch_jobs():
    jobs = db.session.execute(select(BatchJob).order_by(BatchJob.id.desc())).scalars().all()
    return jsonify([job.to_dict() for job in jobs])


@batch_bp.get("/jobs/<int:job_id>")
def get_batch_job(job_id: int):
    job = db.session.get(BatchJob, job_id)
    if job is None:
        return jsonify({"error": "Batch job not found."}), 404

    rows = (
        db.session.execute(
            select(BatchJobRow)
            .where(BatchJobRow.job_id == job.id)
            .order_by(BatchJobRow.row_index.asc())
        )
        .scalars()
        .all()
    )

    return jsonify(
        {
            **job.to_dict(),
            "rows": [row.to_dict() for row in rows],
        }
    )


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
    app.register_blueprint(batch_bp)
    return app
